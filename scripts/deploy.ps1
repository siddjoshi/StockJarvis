# scripts/deploy.ps1 - Windows PowerShell deployment script for StockJarvis

param(
    [Parameter(Position=0)]
    [string]$Command = "deploy"
)

# Configuration
$ErrorActionPreference = "Stop"
$ProjectDir = Split-Path -Parent $PSScriptRoot
$EnvFile = Join-Path $ProjectDir ".env"
$ComposeFile = Join-Path $ProjectDir "docker-compose.yml"
$Timeout = 300  # 5 minutes

# Colors
function Write-Info { Write-Host "[INFO] $args" -ForegroundColor Blue }
function Write-Success { Write-Host "[SUCCESS] $args" -ForegroundColor Green }
function Write-Warning { Write-Host "[WARNING] $args" -ForegroundColor Yellow }
function Write-ErrorMsg { Write-Host "[ERROR] $args" -ForegroundColor Red }
function Write-Header { 
    Write-Host "`n====================================================" -ForegroundColor Blue
    Write-Host $args -ForegroundColor Blue
    Write-Host "====================================================`n" -ForegroundColor Blue
}

function Test-Prerequisites {
    Write-Header "Checking Prerequisites"
    
    # Check Docker
    try {
        $dockerVersion = docker --version
        Write-Success "Docker found: $dockerVersion"
    } catch {
        Write-ErrorMsg "Docker is not installed. Please install Docker Desktop first."
        exit 1
    }
    
    # Check Docker Compose
    try {
        docker-compose version | Out-Null
        Write-Success "Docker Compose found"
    } catch {
        try {
            docker compose version | Out-Null
            Write-Success "Docker Compose (plugin) found"
        } catch {
            Write-ErrorMsg "Docker Compose is not installed."
            exit 1
        }
    }
    
    # Check .env file
    if (-not (Test-Path $EnvFile)) {
        Write-ErrorMsg ".env file not found. Please create it from .env.docker"
        exit 1
    }
    Write-Success ".env file found"
    
    # Check docker-compose.yml
    if (-not (Test-Path $ComposeFile)) {
        Write-ErrorMsg "docker-compose.yml not found"
        exit 1
    }
    Write-Success "docker-compose.yml found"
}

function Stop-Services {
    Write-Header "Stopping Existing Services"
    Set-Location $ProjectDir
    try {
        docker-compose down 2>$null
    } catch {
        docker compose down 2>$null
    }
    Write-Success "Services stopped"
}

function Build-Images {
    Write-Header "Building Docker Images"
    Set-Location $ProjectDir
    try {
        docker-compose build --no-cache
    } catch {
        docker compose build --no-cache
    }
    Write-Success "Images built successfully"
}

function Start-Services {
    Write-Header "Starting Services"
    Set-Location $ProjectDir
    try {
        docker-compose up -d
    } catch {
        docker compose up -d
    }
    Write-Success "Services started"
}

function Wait-ForService {
    param(
        [string]$ServiceName
    )
    
    $maxAttempts = [math]::Floor($Timeout / 10)
    $attempt = 1
    
    Write-Info "Waiting for $ServiceName to be healthy..."
    
    while ($attempt -le $maxAttempts) {
        try {
            $status = docker-compose ps $ServiceName 2>$null | Select-String "Up.*healthy"
            if ($status) {
                Write-Success "$ServiceName is healthy"
                return $true
            }
        } catch {
            # Continue waiting
        }
        
        Write-Host "." -NoNewline
        Start-Sleep -Seconds 10
        $attempt++
    }
    
    Write-Host ""
    Write-ErrorMsg "$ServiceName failed to become healthy within timeout"
    return $false
}

function Test-ServicesHealth {
    Write-Header "Checking Services Health"
    
    $services = @("mysql", "redis", "api", "celery_worker", "flower")
    $allHealthy = $true
    
    foreach ($service in $services) {
        if (-not (Wait-ForService -ServiceName $service)) {
            $allHealthy = $false
        }
    }
    
    if ($allHealthy) {
        Write-Success "All services are healthy"
        return $true
    } else {
        Write-ErrorMsg "Some services are not healthy"
        return $false
    }
}

function Show-ServiceStatus {
    Write-Header "Service Status"
    Set-Location $ProjectDir
    try {
        docker-compose ps
    } catch {
        docker compose ps
    }
}

function Show-Logs {
    Write-Header "Recent Logs"
    Set-Location $ProjectDir
    try {
        docker-compose logs --tail=50
    } catch {
        docker compose logs --tail=50
    }
}

function Show-Endpoints {
    Write-Header "Service Endpoints"
    Write-Host "FastAPI Application: " -NoNewline -ForegroundColor Green
    Write-Host "http://localhost:8000"
    Write-Host "API Documentation: " -NoNewline -ForegroundColor Green
    Write-Host "http://localhost:8000/docs"
    Write-Host "Flower Dashboard: " -NoNewline -ForegroundColor Green
    Write-Host "http://localhost:5555"
    Write-Host "MySQL: " -NoNewline -ForegroundColor Green
    Write-Host "localhost:3306"
    Write-Host "Redis: " -NoNewline -ForegroundColor Green
    Write-Host "localhost:6379"
}

function Test-API {
    Write-Header "Testing API Endpoint"
    
    $maxAttempts = 30
    $attempt = 1
    
    while ($attempt -le $maxAttempts) {
        try {
            $response = Invoke-WebRequest -Uri "http://localhost:8000/health" -UseBasicParsing -TimeoutSec 2
            if ($response.StatusCode -eq 200) {
                Write-Success "API is responding"
                $response.Content | ConvertFrom-Json | ConvertTo-Json
                return $true
            }
        } catch {
            # Continue waiting
        }
        
        Write-Host "." -NoNewline
        Start-Sleep -Seconds 2
        $attempt++
    }
    
    Write-Host ""
    Write-ErrorMsg "API is not responding"
    return $false
}

function New-Backup {
    Write-Header "Creating Backup"
    
    $backupDir = Join-Path $ProjectDir "backups"
    $timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $backupFile = Join-Path $backupDir "stockjarvis_backup_$timestamp.sql"
    
    if (-not (Test-Path $backupDir)) {
        New-Item -ItemType Directory -Path $backupDir | Out-Null
    }
    
    # Load environment variables
    Get-Content $EnvFile | ForEach-Object {
        if ($_ -match '^([^=]+)=(.*)$') {
            Set-Item -Path "env:$($Matches[1])" -Value $Matches[2]
        }
    }
    
    Write-Info "Backing up database..."
    $dbUser = $env:DB_USER
    $dbPassword = $env:DB_PASSWORD
    $dbDatabase = if ($env:DB_DATABASE) { $env:DB_DATABASE } else { "stockjarvis" }
    
    docker-compose exec -T mysql mysqldump -u$dbUser -p$dbPassword $dbDatabase | Out-File -FilePath $backupFile -Encoding UTF8
    
    if (Test-Path $backupFile) {
        Write-Success "Backup created: $backupFile"
    } else {
        Write-ErrorMsg "Backup failed"
        return $false
    }
}

function Show-Help {
    @"
StockJarvis Deployment Script (PowerShell)

Usage: .\scripts\deploy.ps1 [COMMAND]

Commands:
    deploy          Full deployment (stop, build, start, health check)
    start           Start services without rebuilding
    stop            Stop all services
    restart         Restart all services
    build           Build Docker images only
    status          Show service status
    logs            Show service logs
    health          Check services health
    backup          Create database backup
    clean           Remove all containers, volumes, and images
    help            Show this help message

Examples:
    .\scripts\deploy.ps1 deploy      # Full deployment
    .\scripts\deploy.ps1 logs        # Show logs
    .\scripts\deploy.ps1 backup      # Create database backup
    .\scripts\deploy.ps1 clean       # Clean up everything

"@
}

function Remove-All {
    Write-Header "Cleaning Up"
    
    $confirmation = Read-Host "This will remove all containers, volumes, and images. Continue? (y/N)"
    
    if ($confirmation -ne 'y' -and $confirmation -ne 'Y') {
        Write-Info "Cleanup cancelled"
        exit 0
    }
    
    Set-Location $ProjectDir
    try {
        docker-compose down -v --rmi all
    } catch {
        docker compose down -v --rmi all
    }
    Write-Success "Cleanup completed"
}

function Start-Deployment {
    Write-Header "StockJarvis Deployment Starting"
    
    Test-Prerequisites
    Stop-Services
    Build-Images
    Start-Services
    
    Start-Sleep -Seconds 10  # Give services time to initialize
    
    if (Test-ServicesHealth) {
        Test-API
        Show-ServiceStatus
        Show-Endpoints
        Write-Success "Deployment completed successfully!"
    } else {
        Write-ErrorMsg "Deployment completed with errors. Check logs for details."
        Show-Logs
        exit 1
    }
}

# Main command handling
switch ($Command.ToLower()) {
    "deploy" {
        Start-Deployment
    }
    "start" {
        Test-Prerequisites
        Start-Services
        Show-ServiceStatus
    }
    "stop" {
        Stop-Services
    }
    "restart" {
        Stop-Services
        Start-Services
        Show-ServiceStatus
    }
    "build" {
        Test-Prerequisites
        Build-Images
    }
    "status" {
        Show-ServiceStatus
    }
    "logs" {
        Set-Location $ProjectDir
        try {
            docker-compose logs --tail=100
        } catch {
            docker compose logs --tail=100
        }
    }
    "health" {
        Test-ServicesHealth
    }
    "backup" {
        New-Backup
    }
    "clean" {
        Remove-All
    }
    "help" {
        Show-Help
    }
    default {
        Write-ErrorMsg "Unknown command: $Command"
        Show-Help
        exit 1
    }
}
