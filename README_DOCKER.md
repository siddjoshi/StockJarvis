# 🐳 Docker Deployment - StockJarvis

Complete Docker containerization for production-ready deployment of StockJarvis automated trading platform.

## 📋 Table of Contents
- [Files Structure](#files-structure)
- [Prerequisites](#prerequisites)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [Deployment Options](#deployment-options)
- [Service Architecture](#service-architecture)
- [Monitoring](#monitoring)
- [Troubleshooting](#troubleshooting)

## 📁 Files Structure

```
StockJarvis/
├── docker-compose.yml          # Production multi-service orchestration
├── docker-compose.dev.yml      # Development setup (MySQL + Redis only)
├── Dockerfile                  # Multi-stage Python application build
├── .dockerignore              # Build context exclusions
├── .env.docker                # Environment variables template
├── DOCKER_DEPLOYMENT.md       # Comprehensive deployment guide
├── DOCKER_COMMANDS.md         # Quick command reference
│
├── docker/
│   ├── mysql/
│   │   ├── init.sql          # Database initialization + sample data
│   │   └── conf.d/
│   │       └── custom.cnf    # MySQL performance tuning
│   └── redis/
│       └── redis.conf        # Redis configuration (persistence, memory)
│
└── scripts/
    ├── deploy.sh             # Linux/Mac deployment script
    └── deploy.ps1            # Windows PowerShell deployment script
```

## ✅ Prerequisites

- **Docker Engine** 20.10+
- **Docker Compose** 2.0+
- **RAM**: 4GB minimum, 8GB recommended
- **Disk**: 10GB minimum, 20GB recommended
- **OS**: Windows 10/11, Linux, macOS

### Verify Installation
```bash
docker --version
docker-compose --version
```

## 🚀 Quick Start

### 1️⃣ Configure Environment
```bash
# Copy environment template
cp .env.docker .env

# Generate secure secret key
openssl rand -hex 32

# Edit .env with your credentials
nano .env  # or use any text editor
```

**Required Changes:**
- `DB_ROOT_PASSWORD` - Strong MySQL root password
- `DB_PASSWORD` - Application database password
- `APP_SECRET_KEY` - Generated secure key from above
- `QUANDL_API_KEY` - Your Quandl API key
- `ZERODHA_API_KEY` & `ZERODHA_API_SECRET` - Broker credentials
- `FLOWER_PASSWORD` - Celery monitoring dashboard password

### 2️⃣ Deploy Services

**Option A: Using Deployment Script (Recommended)**
```bash
# Linux/Mac
chmod +x scripts/deploy.sh
./scripts/deploy.sh deploy

# Windows PowerShell
.\scripts\deploy.ps1 deploy
```

**Option B: Using Docker Compose**
```bash
# Build and start all services
docker-compose up -d --build

# Check status
docker-compose ps

# View logs
docker-compose logs -f
```

### 3️⃣ Verify Deployment
```bash
# Check API health
curl http://localhost:8000/health

# Access services
open http://localhost:8000/docs       # API Documentation
open http://localhost:5555             # Flower Dashboard
```

## ⚙️ Configuration

### Environment Variables

| Category | Variable | Description | Default |
|----------|----------|-------------|---------|
| **Database** | DB_HOST | MySQL host | mysql |
| | DB_PORT | MySQL port | 3306 |
| | DB_USER | Database user | jarvis |
| | DB_PASSWORD | Database password | *(required)* |
| | DB_DATABASE | Database name | stockjarvis |
| **Redis** | REDIS_HOST | Redis host | redis |
| | REDIS_PORT | Redis port | 6379 |
| | REDIS_PASSWORD | Redis password | *(empty)* |
| **Trading** | TRADING_MODE | Trading mode | paper |
| | TRADING_CAPITAL | Starting capital | 100000 |
| | TRADING_MAX_POSITIONS | Max positions | 5 |
| **API** | APP_SECRET_KEY | JWT secret | *(required)* |
| | APP_LOG_LEVEL | Logging level | INFO |
| | APP_ENV | Environment | production |

### Service Ports

| Service | Port | Description |
|---------|------|-------------|
| API | 8000 | FastAPI application |
| Flower | 5555 | Celery monitoring |
| MySQL | 3306 | Database (internal + external) |
| Redis | 6379 | Cache/Queue (internal + external) |

### Resource Limits

| Service | Memory Limit | CPU Limit | Replicas |
|---------|--------------|-----------|----------|
| MySQL | 2GB | 2.0 | 1 |
| Redis | 512MB | 0.5 | 1 |
| API | 1GB | 1.0 | 1 |
| Worker | 2GB | 2.0 | 1* |
| Beat | 512MB | 0.5 | 1 |
| Flower | 256MB | 0.25 | 1 |

\* Worker can be scaled: `docker-compose up -d --scale celery_worker=4`

## 🎯 Deployment Options

### Development Mode
```bash
# Start only MySQL and Redis
docker-compose -f docker-compose.dev.yml up -d

# Run application locally
python -m uvicorn api.main:app --reload
```

### Production Mode
```bash
# Full deployment
./scripts/deploy.sh deploy

# With custom env file
docker-compose --env-file .env.production up -d
```

### Staging Mode
```bash
# Copy production config
cp .env .env.staging

# Edit for staging
nano .env.staging

# Deploy
docker-compose --env-file .env.staging up -d
```

## 🏗️ Service Architecture

```
                    ┌─────────────────────────┐
                    │   Load Balancer/Nginx   │
                    │      (Optional)         │
                    └────────────┬────────────┘
                                 │
                    ┌────────────▼────────────┐
                    │     API Gateway         │
                    │   FastAPI :8000         │
                    └─────┬──────────┬────────┘
                          │          │
            ┌─────────────▼───┐      │
            │   MySQL :3306   │      │
            │   (MariaDB)     │      │
            │  - Prices       │      │
            │  - Signals      │      │
            │  - Positions    │      │
            └─────────────────┘      │
                                     │
            ┌────────────────────────▼──────┐
            │       Redis :6379             │
            │   - Task Queue                │
            │   - Cache                     │
            │   - Pub/Sub                   │
            └────┬────────────┬─────────────┘
                 │            │
     ┌───────────▼─────┐     ┌▼──────────────┐
     │ Celery Worker   │     │  Celery Beat  │
     │ (Background)    │     │  (Scheduler)  │
     │ - Data Collection│     │  - Cron Jobs  │
     │ - Signal Gen    │     └───────────────┘
     │ - Risk Mgmt     │
     └─────────────────┘
                 │
        ┌────────▼──────────┐
        │   Flower :5555    │
        │   (Monitoring)    │
        └───────────────────┘
```

### Service Dependencies

1. **MySQL** - Core database, must start first
2. **Redis** - Task queue & cache
3. **API** - Depends on MySQL + Redis
4. **Celery Worker** - Depends on MySQL + Redis
5. **Celery Beat** - Depends on MySQL + Redis
6. **Flower** - Depends on Redis

## 📊 Monitoring

### Health Checks

All services have automated health checks:

```bash
# Check all service health
docker-compose ps

# Detailed health status
docker inspect --format='{{.State.Health.Status}}' stockjarvis_api
```

### Logs

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f api

# With timestamps
docker-compose logs -f --timestamps api

# Last 100 lines
docker-compose logs --tail=100
```

### Metrics

Access Flower dashboard for real-time metrics:
- URL: http://localhost:5555
- Username: admin (from .env)
- Password: (from .env FLOWER_PASSWORD)

**Available Metrics:**
- Active/processed/failed tasks
- Worker status
- Task execution times
- Queue lengths

### Resource Monitoring

```bash
# Real-time stats
docker stats

# Specific containers
docker stats stockjarvis_api stockjarvis_mysql
```

## 🔧 Troubleshooting

### Services Not Starting

**Check logs:**
```bash
docker-compose logs mysql
docker-compose logs api
```

**Common issues:**
- Port already in use → Change port in docker-compose.yml
- Missing .env file → Copy from .env.docker
- Database not ready → Wait for health check or increase timeout

### Database Connection Failed

```bash
# Check MySQL status
docker-compose ps mysql

# Test connection
docker-compose exec mysql mysql -u${DB_USER} -p${DB_PASSWORD} -e "SELECT 1;"

# View MySQL logs
docker-compose logs mysql | grep -i error
```

### API Not Responding

```bash
# Check API logs
docker-compose logs api | tail -50

# Test inside container
docker-compose exec api curl localhost:8000/health

# Restart API
docker-compose restart api
```

### Celery Worker Issues

```bash
# Check worker status
docker-compose exec celery_worker celery -A workers.celery_app inspect active

# View worker logs
docker-compose logs celery_worker | grep -i error

# Restart worker
docker-compose restart celery_worker
```

### Out of Memory

```bash
# Check memory usage
docker stats

# Increase service limits in docker-compose.yml
# Or scale down workers
docker-compose up -d --scale celery_worker=1
```

### Clean Restart

```bash
# Stop all services
docker-compose down

# Remove volumes (WARNING: deletes data)
docker-compose down -v

# Rebuild and start fresh
docker-compose up -d --build
```

## 🔐 Security Checklist

- [ ] Changed all default passwords in .env
- [ ] Generated secure APP_SECRET_KEY
- [ ] Set TRADING_MODE=paper for testing
- [ ] Configured firewall rules
- [ ] Disabled debug mode (APP_DEBUG=false)
- [ ] Set appropriate log level (WARNING/ERROR)
- [ ] Secured Flower dashboard credentials
- [ ] Regular backups configured
- [ ] SSL/TLS configured for API (if public)
- [ ] Environment variables not in version control

## 💾 Backup & Recovery

### Automated Backup
```bash
# Create backup
./scripts/deploy.sh backup

# Or manually
docker-compose exec mysql mysqldump -u${DB_USER} -p${DB_PASSWORD} stockjarvis > backup_$(date +%Y%m%d).sql
```

### Restore
```bash
# Restore database
docker-compose exec -T mysql mysql -u${DB_USER} -p${DB_PASSWORD} stockjarvis < backup.sql
```

### Volume Backup
```bash
# Backup volumes
docker run --rm -v stockjarvis_mysql_data:/data -v $(pwd):/backup alpine tar czf /backup/mysql_data.tar.gz -C /data .
```

## 📚 Additional Documentation

- [DOCKER_COMMANDS.md](DOCKER_COMMANDS.md) - Command reference
- [DOCKER_DEPLOYMENT.md](DOCKER_DEPLOYMENT.md) - Detailed deployment guide
- [README.md](README.md) - Main project documentation

## 🆘 Support

**Common Commands:**
```bash
# View all commands
./scripts/deploy.sh help

# Check service status
docker-compose ps

# View logs
docker-compose logs -f

# Restart service
docker-compose restart <service>

# Stop everything
docker-compose down
```

**Need help?** Check the troubleshooting section or open an issue.

---

**⚠️ IMPORTANT REMINDERS:**
- Always test in `paper` trading mode first
- Never commit `.env` file to git
- Regularly backup your database
- Monitor logs for errors
- Keep Docker images updated
