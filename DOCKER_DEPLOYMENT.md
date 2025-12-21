# Docker Deployment Guide for StockJarvis

Complete Docker deployment setup with multi-service orchestration.

## 📦 Files Created

1. **docker-compose.yml** - 6-service orchestration (MySQL, Redis, API, Celery Worker, Beat, Flower)
2. **Dockerfile** - Multi-stage build with security best practices
3. **.dockerignore** - Optimized build context
4. **docker/mysql/init.sql** - Database initialization with sample data
5. **docker/redis/redis.conf** - Redis configuration with persistence
6. **docker/mysql/conf.d/custom.cnf** - MySQL performance tuning
7. **scripts/deploy.sh** - Automated deployment script
8. **.env.docker** - Environment variables template

## 🚀 Quick Start

### 1. Prerequisites
- Docker Engine 20.10+
- Docker Compose 2.0+
- 4GB RAM minimum
- 10GB disk space

### 2. Setup Environment

```bash
# Copy environment template
cp .env.docker .env

# Generate secure secret key
openssl rand -hex 32

# Edit .env and update:
# - DB_ROOT_PASSWORD
# - DB_PASSWORD
# - APP_SECRET_KEY
# - API keys (Quandl, Zerodha)
# - FLOWER_PASSWORD
```

### 3. Deploy

```bash
# Make deploy script executable (Linux/Mac)
chmod +x scripts/deploy.sh

# Run full deployment
./scripts/deploy.sh deploy

# Or using docker-compose directly
docker-compose up -d --build
```

### 4. Verify Deployment

```bash
# Check service status
docker-compose ps

# View logs
docker-compose logs -f

# Test API health
curl http://localhost:8000/health
```

## 🌐 Service Endpoints

| Service | URL | Description |
|---------|-----|-------------|
| API | http://localhost:8000 | FastAPI application |
| API Docs | http://localhost:8000/docs | Swagger UI |
| Flower | http://localhost:5555 | Celery monitoring |
| MySQL | localhost:3306 | Database |
| Redis | localhost:6379 | Cache/Queue |

## 🛠️ Management Commands

```bash
# Start services
./scripts/deploy.sh start

# Stop services
./scripts/deploy.sh stop

# Restart services
./scripts/deploy.sh restart

# View logs (follow mode)
./scripts/deploy.sh logs -f

# Check health
./scripts/deploy.sh health

# Create database backup
./scripts/deploy.sh backup

# Clean all (removes volumes!)
./scripts/deploy.sh clean
```

## 📊 Service Architecture

```
┌─────────────────────────────────────────────────────────┐
│                     External Access                      │
├─────────┬──────────┬────────────┬──────────┬────────────┤
│  :8000  │  :5555   │   :3306    │  :6379   │            │
└────┬────┴────┬─────┴──────┬─────┴────┬─────┴────────────┘
     │         │            │          │
┌────▼─────────▼────────────▼──────────▼──────────────────┐
│            Docker Network (Bridge)                       │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌─────────┐ │
│  │   API    │  │  Worker  │  │   Beat   │  │ Flower  │ │
│  │  :8000   │  │  Celery  │  │  Celery  │  │  :5555  │ │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬────┘ │
│       │             │             │             │       │
│  ┌────▼─────────────▼─────────────▼─────────────▼────┐ │
│  │              MySQL :3306                           │ │
│  │         (MariaDB 10.11 + Volumes)                  │ │
│  └──────────────────────────────────────────────────── │ │
│  ┌────────────────────────────────────────────────────┐ │
│  │              Redis :6379                           │ │
│  │         (Redis 7 + Persistence)                    │ │
│  └────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

## 🔒 Security Features

- Non-root user in containers
- Read-only filesystems where possible
- Health checks for all services
- Resource limits (CPU/Memory)
- Disabled dangerous Redis commands
- Environment-based secrets
- Network isolation
- Secure password handling

## 📦 Volumes & Data Persistence

| Volume | Purpose | Location |
|--------|---------|----------|
| mysql_data | Database files | /var/lib/mysql |
| redis_data | Redis persistence | /data |
| api_data | API application data | /app/data |
| worker_data | Celery worker data | /app/data |
| beat_data | Celery beat scheduler | /app/data |

## 🧪 Testing

```bash
# Test API endpoint
curl http://localhost:8000/health

# Test database connection
docker-compose exec mysql mysql -u${DB_USER} -p${DB_PASSWORD} -e "SHOW DATABASES;"

# Test Redis
docker-compose exec redis redis-cli ping

# Check Celery workers
docker-compose exec celery_worker celery -A workers.celery_app inspect active
```

## 📝 Logs

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f api
docker-compose logs -f celery_worker

# Last 100 lines
docker-compose logs --tail=100

# Application logs (mounted volume)
tail -f logs/jarvis.log
```

## 🔧 Troubleshooting

### Services not starting
```bash
# Check logs
docker-compose logs

# Check resource usage
docker stats

# Restart specific service
docker-compose restart api
```

### Database connection issues
```bash
# Verify MySQL is healthy
docker-compose ps mysql

# Test connection
docker-compose exec mysql mysql -u${DB_USER} -p${DB_PASSWORD} -e "SELECT 1;"

# Check init script execution
docker-compose logs mysql | grep -i "init"
```

### Redis connection issues
```bash
# Check Redis
docker-compose exec redis redis-cli ping

# View Redis logs
docker-compose logs redis
```

### API not responding
```bash
# Check API logs
docker-compose logs api

# Verify dependencies
docker-compose exec api pip list

# Test inside container
docker-compose exec api curl localhost:8000/health
```

## 🔄 Updates & Maintenance

### Update application code
```bash
# Pull latest code
git pull

# Rebuild and restart
docker-compose up -d --build
```

### Database migrations
```bash
# Run Alembic migrations
docker-compose exec api alembic upgrade head

# Or manually
docker-compose exec mysql mysql -u${DB_USER} -p${DB_PASSWORD} stockjarvis < migration.sql
```

### Backup & Restore
```bash
# Backup
./scripts/deploy.sh backup

# Restore
docker-compose exec -T mysql mysql -u${DB_USER} -p${DB_PASSWORD} stockjarvis < backup.sql
```

## 🚀 Production Deployment

1. **Update .env for production**
   - Set strong passwords
   - Configure TRADING_MODE=paper (test first!)
   - Set APP_DEBUG=false
   - Set APP_LOG_LEVEL=WARNING
   - Configure real notification credentials

2. **Enable SSL/TLS**
   - Add Nginx reverse proxy
   - Configure SSL certificates
   - Update CORS settings

3. **Monitoring**
   - Set up log aggregation
   - Configure alerting
   - Monitor Flower dashboard

4. **Scaling**
   ```bash
   # Scale workers
   docker-compose up -d --scale celery_worker=4
   ```

## 📚 Additional Resources

- [Docker Compose Documentation](https://docs.docker.com/compose/)
- [FastAPI Deployment](https://fastapi.tiangolo.com/deployment/)
- [Celery Best Practices](https://docs.celeryproject.org/en/stable/)
- [Redis Configuration](https://redis.io/topics/config)

## ⚠️ Important Notes

- **Always test in paper trading mode first**
- **Never commit .env file to version control**
- **Regularly backup database and volumes**
- **Monitor resource usage in production**
- **Keep Docker images updated**
- **Review logs regularly for errors**

## 📄 License

Same as StockJarvis main project.
