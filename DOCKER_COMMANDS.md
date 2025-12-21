# Quick Docker Commands Reference

## 🚀 Quick Start

```powershell
# Windows (PowerShell)
.\scripts\deploy.ps1 deploy

# Linux/Mac (Bash)
./scripts/deploy.sh deploy
```

## 📦 Docker Compose Commands

### Start/Stop Services
```bash
# Start all services
docker-compose up -d

# Start specific service
docker-compose up -d api

# Stop all services
docker-compose stop

# Stop and remove containers
docker-compose down

# Stop and remove everything (including volumes)
docker-compose down -v
```

### Build & Rebuild
```bash
# Build images
docker-compose build

# Build with no cache
docker-compose build --no-cache

# Build specific service
docker-compose build api

# Build and start
docker-compose up -d --build
```

### View Services
```bash
# List running containers
docker-compose ps

# View service logs
docker-compose logs

# Follow logs (real-time)
docker-compose logs -f

# Logs for specific service
docker-compose logs -f api

# Last 100 lines
docker-compose logs --tail=100
```

### Execute Commands
```bash
# Execute command in running container
docker-compose exec api bash

# Run Python shell
docker-compose exec api python

# Run database query
docker-compose exec mysql mysql -u$DB_USER -p$DB_PASSWORD stockjarvis

# Run Redis CLI
docker-compose exec redis redis-cli

# Check Celery workers
docker-compose exec celery_worker celery -A workers.celery_app inspect active
```

## 🔍 Troubleshooting Commands

### Check Container Status
```bash
# List all containers
docker ps -a

# Check resource usage
docker stats

# Inspect container
docker inspect stockjarvis_api

# View container logs
docker logs stockjarvis_api

# Follow container logs
docker logs -f stockjarvis_api
```

### Network Debugging
```bash
# List networks
docker network ls

# Inspect network
docker network inspect stockjarvis_network

# Test connectivity between containers
docker-compose exec api ping mysql
docker-compose exec api ping redis
```

### Database Operations
```bash
# Connect to MySQL
docker-compose exec mysql mysql -u$DB_USER -p$DB_PASSWORD stockjarvis

# Run SQL file
docker-compose exec -T mysql mysql -u$DB_USER -p$DB_PASSWORD stockjarvis < script.sql

# Dump database
docker-compose exec mysql mysqldump -u$DB_USER -p$DB_PASSWORD stockjarvis > backup.sql

# Restore database
docker-compose exec -T mysql mysql -u$DB_USER -p$DB_PASSWORD stockjarvis < backup.sql

# Check database size
docker-compose exec mysql mysql -u$DB_USER -p$DB_PASSWORD -e "SELECT table_schema AS 'Database', ROUND(SUM(data_length + index_length) / 1024 / 1024, 2) AS 'Size (MB)' FROM information_schema.TABLES GROUP BY table_schema;"
```

### Redis Operations
```bash
# Connect to Redis
docker-compose exec redis redis-cli

# Check keys
docker-compose exec redis redis-cli KEYS "*"

# Monitor Redis commands
docker-compose exec redis redis-cli MONITOR

# Check memory usage
docker-compose exec redis redis-cli INFO memory

# Flush all data (DANGEROUS!)
docker-compose exec redis redis-cli FLUSHALL
```

### Celery Operations
```bash
# Check active tasks
docker-compose exec celery_worker celery -A workers.celery_app inspect active

# Check registered tasks
docker-compose exec celery_worker celery -A workers.celery_app inspect registered

# Check worker stats
docker-compose exec celery_worker celery -A workers.celery_app inspect stats

# Purge all tasks
docker-compose exec celery_worker celery -A workers.celery_app purge

# Restart worker
docker-compose restart celery_worker
```

## 🧹 Cleanup Commands

### Remove Containers
```bash
# Remove stopped containers
docker-compose rm

# Force remove
docker-compose rm -f

# Remove specific service
docker-compose rm -f api
```

### Remove Images
```bash
# Remove project images
docker-compose down --rmi local

# Remove all images
docker-compose down --rmi all

# Remove unused images
docker image prune

# Remove all unused images
docker image prune -a
```

### Remove Volumes
```bash
# Remove named volumes
docker-compose down -v

# List volumes
docker volume ls

# Remove specific volume
docker volume rm stockjarvis_mysql_data

# Remove all unused volumes
docker volume prune
```

### Full Cleanup
```bash
# Remove everything (DANGEROUS!)
docker-compose down -v --rmi all

# System-wide cleanup
docker system prune -a --volumes
```

## 📊 Monitoring Commands

### Resource Usage
```bash
# Real-time stats
docker stats

# Stats for specific containers
docker stats stockjarvis_api stockjarvis_mysql

# Format output
docker stats --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}"
```

### Health Checks
```bash
# Check health status
docker inspect --format='{{.State.Health.Status}}' stockjarvis_api

# View health check logs
docker inspect --format='{{range .State.Health.Log}}{{.Output}}{{end}}' stockjarvis_api
```

### Disk Usage
```bash
# Show disk usage
docker system df

# Detailed disk usage
docker system df -v
```

## 🔧 Maintenance Commands

### Update Images
```bash
# Pull latest images
docker-compose pull

# Rebuild and restart
docker-compose up -d --build
```

### Scale Services
```bash
# Scale workers
docker-compose up -d --scale celery_worker=4

# Scale back
docker-compose up -d --scale celery_worker=2
```

### Restart Services
```bash
# Restart all services
docker-compose restart

# Restart specific service
docker-compose restart api

# Restart with timeout
docker-compose restart -t 30 api
```

## 💾 Backup & Restore

### Database Backup
```bash
# Create backup
docker-compose exec mysql mysqldump -u$DB_USER -p$DB_PASSWORD stockjarvis > backup_$(date +%Y%m%d_%H%M%S).sql

# Compressed backup
docker-compose exec mysql mysqldump -u$DB_USER -p$DB_PASSWORD stockjarvis | gzip > backup_$(date +%Y%m%d_%H%M%S).sql.gz

# Restore backup
docker-compose exec -T mysql mysql -u$DB_USER -p$DB_PASSWORD stockjarvis < backup.sql

# Restore compressed backup
gunzip < backup.sql.gz | docker-compose exec -T mysql mysql -u$DB_USER -p$DB_PASSWORD stockjarvis
```

### Volume Backup
```bash
# Backup MySQL volume
docker run --rm -v stockjarvis_mysql_data:/data -v $(pwd):/backup alpine tar czf /backup/mysql_backup.tar.gz -C /data .

# Restore MySQL volume
docker run --rm -v stockjarvis_mysql_data:/data -v $(pwd):/backup alpine tar xzf /backup/mysql_backup.tar.gz -C /data
```

## 🐛 Debug Mode

### Interactive Shell
```bash
# Bash shell in API container
docker-compose exec api bash

# Python REPL
docker-compose exec api python

# IPython (if installed)
docker-compose exec api ipython
```

### Run Tests
```bash
# Run tests in container
docker-compose exec api pytest

# Run with coverage
docker-compose exec api pytest --cov=.

# Run specific test file
docker-compose exec api pytest tests/test_strategies.py
```

### View Environment Variables
```bash
# Show all env vars
docker-compose exec api env

# Show specific env var
docker-compose exec api printenv DB_HOST
```

## 📝 Useful Aliases (Add to ~/.bashrc or PowerShell profile)

### Bash
```bash
alias dcu='docker-compose up -d'
alias dcd='docker-compose down'
alias dcl='docker-compose logs -f'
alias dcp='docker-compose ps'
alias dcr='docker-compose restart'
alias dcb='docker-compose build'
```

### PowerShell
```powershell
function dcu { docker-compose up -d }
function dcd { docker-compose down }
function dcl { docker-compose logs -f }
function dcp { docker-compose ps }
function dcr { docker-compose restart }
function dcb { docker-compose build }
```

## 🔐 Security Commands

### Scan for Vulnerabilities
```bash
# Scan image
docker scan stockjarvis_api:latest

# Scan with detailed output
docker scan --severity high stockjarvis_api:latest
```

### Update Passwords
```bash
# Change MySQL password
docker-compose exec mysql mysql -u root -p -e "ALTER USER '$DB_USER'@'%' IDENTIFIED BY 'new_password';"

# Update .env file and restart
vim .env
docker-compose up -d --force-recreate mysql api
```

## 📚 Additional Resources

- [Docker Documentation](https://docs.docker.com/)
- [Docker Compose CLI Reference](https://docs.docker.com/compose/reference/)
- [Dockerfile Best Practices](https://docs.docker.com/develop/develop-images/dockerfile_best-practices/)
- [Docker Security](https://docs.docker.com/engine/security/)
