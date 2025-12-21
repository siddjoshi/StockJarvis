#!/bin/bash
# scripts/deploy.sh - StockJarvis deployment script

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
ENV_FILE="${PROJECT_DIR}/.env"
COMPOSE_FILE="${PROJECT_DIR}/docker-compose.yml"
TIMEOUT=300  # 5 minutes timeout for health checks

# Functions
print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_header() {
    echo -e "\n${BLUE}===================================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}===================================================${NC}\n"
}

check_prerequisites() {
    print_header "Checking Prerequisites"
    
    # Check Docker
    if ! command -v docker &> /dev/null; then
        print_error "Docker is not installed. Please install Docker first."
        exit 1
    fi
    print_success "Docker found: $(docker --version)"
    
    # Check Docker Compose
    if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
        print_error "Docker Compose is not installed. Please install Docker Compose first."
        exit 1
    fi
    print_success "Docker Compose found"
    
    # Check .env file
    if [ ! -f "$ENV_FILE" ]; then
        print_error ".env file not found. Please create it from .env.example"
        exit 1
    fi
    print_success ".env file found"
    
    # Check docker-compose.yml
    if [ ! -f "$COMPOSE_FILE" ]; then
        print_error "docker-compose.yml not found"
        exit 1
    fi
    print_success "docker-compose.yml found"
}

stop_services() {
    print_header "Stopping Existing Services"
    cd "$PROJECT_DIR"
    docker-compose down || docker compose down || true
    print_success "Services stopped"
}

build_images() {
    print_header "Building Docker Images"
    cd "$PROJECT_DIR"
    docker-compose build --no-cache || docker compose build --no-cache
    print_success "Images built successfully"
}

start_services() {
    print_header "Starting Services"
    cd "$PROJECT_DIR"
    docker-compose up -d || docker compose up -d
    print_success "Services started"
}

wait_for_service() {
    local service_name=$1
    local health_check_url=$2
    local max_attempts=$((TIMEOUT / 10))
    local attempt=1
    
    print_info "Waiting for $service_name to be healthy..."
    
    while [ $attempt -le $max_attempts ]; do
        if docker-compose ps "$service_name" | grep -q "Up (healthy)"; then
            print_success "$service_name is healthy"
            return 0
        fi
        
        echo -n "."
        sleep 10
        attempt=$((attempt + 1))
    done
    
    print_error "$service_name failed to become healthy within timeout"
    return 1
}

check_services_health() {
    print_header "Checking Services Health"
    
    local services=("mysql" "redis" "api" "celery_worker" "flower")
    local all_healthy=true
    
    for service in "${services[@]}"; do
        if ! wait_for_service "$service"; then
            all_healthy=false
        fi
    done
    
    if [ "$all_healthy" = true ]; then
        print_success "All services are healthy"
        return 0
    else
        print_error "Some services are not healthy"
        return 1
    fi
}

show_service_status() {
    print_header "Service Status"
    cd "$PROJECT_DIR"
    docker-compose ps || docker compose ps
}

show_logs() {
    print_header "Recent Logs"
    cd "$PROJECT_DIR"
    docker-compose logs --tail=50 || docker compose logs --tail=50
}

show_endpoints() {
    print_header "Service Endpoints"
    echo -e "${GREEN}FastAPI Application:${NC} http://localhost:8000"
    echo -e "${GREEN}API Documentation:${NC} http://localhost:8000/docs"
    echo -e "${GREEN}Flower Dashboard:${NC} http://localhost:5555"
    echo -e "${GREEN}MySQL:${NC} localhost:3306"
    echo -e "${GREEN}Redis:${NC} localhost:6379"
}

test_api() {
    print_header "Testing API Endpoint"
    
    local max_attempts=30
    local attempt=1
    
    while [ $attempt -le $max_attempts ]; do
        if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
            print_success "API is responding"
            curl -s http://localhost:8000/health | python -m json.tool || echo ""
            return 0
        fi
        
        echo -n "."
        sleep 2
        attempt=$((attempt + 1))
    done
    
    print_error "API is not responding"
    return 1
}

create_backup() {
    print_header "Creating Backup"
    
    local backup_dir="${PROJECT_DIR}/backups"
    local timestamp=$(date +%Y%m%d_%H%M%S)
    local backup_file="${backup_dir}/stockjarvis_backup_${timestamp}.sql"
    
    mkdir -p "$backup_dir"
    
    print_info "Backing up database..."
    docker-compose exec -T mysql mysqldump -u${DB_USER} -p${DB_PASSWORD} ${DB_DATABASE:-stockjarvis} > "$backup_file"
    
    if [ -f "$backup_file" ]; then
        print_success "Backup created: $backup_file"
    else
        print_error "Backup failed"
        return 1
    fi
}

show_help() {
    cat << EOF
StockJarvis Deployment Script

Usage: $0 [COMMAND]

Commands:
    deploy          Full deployment (stop, build, start, health check)
    start           Start services without rebuilding
    stop            Stop all services
    restart         Restart all services
    build           Build Docker images only
    status          Show service status
    logs            Show service logs (use -f to follow)
    health          Check services health
    backup          Create database backup
    clean           Remove all containers, volumes, and images
    help            Show this help message

Examples:
    $0 deploy              # Full deployment
    $0 logs -f             # Follow logs
    $0 backup              # Create database backup
    $0 clean               # Clean up everything

EOF
}

clean_all() {
    print_header "Cleaning Up"
    
    read -p "This will remove all containers, volumes, and images. Continue? (y/N) " -n 1 -r
    echo
    
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        print_info "Cleanup cancelled"
        exit 0
    fi
    
    cd "$PROJECT_DIR"
    docker-compose down -v --rmi all || docker compose down -v --rmi all
    print_success "Cleanup completed"
}

# Main deployment function
deploy() {
    print_header "StockJarvis Deployment Starting"
    
    check_prerequisites
    stop_services
    build_images
    start_services
    
    sleep 10  # Give services time to initialize
    
    if check_services_health; then
        test_api
        show_service_status
        show_endpoints
        print_success "Deployment completed successfully!"
    else
        print_error "Deployment completed with errors. Check logs for details."
        show_logs
        exit 1
    fi
}

# Command handling
case "${1:-deploy}" in
    deploy)
        deploy
        ;;
    start)
        check_prerequisites
        start_services
        show_service_status
        ;;
    stop)
        stop_services
        ;;
    restart)
        stop_services
        start_services
        show_service_status
        ;;
    build)
        check_prerequisites
        build_images
        ;;
    status)
        show_service_status
        ;;
    logs)
        cd "$PROJECT_DIR"
        shift
        docker-compose logs "$@" || docker compose logs "$@"
        ;;
    health)
        check_services_health
        ;;
    backup)
        create_backup
        ;;
    clean)
        clean_all
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        print_error "Unknown command: $1"
        show_help
        exit 1
        ;;
esac
