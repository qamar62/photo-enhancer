# Deployment Guide for Proxmox

Complete guide to deploy the Passport Photo Enhancer on Proxmox and route it to `photo.qaam.work`.

## Prerequisites

- Proxmox server with Docker and Docker Compose installed
- Domain `photo.qaam.work` pointing to your Proxmox server IP
- SSL certificate for `photo.qaam.work` (Let's Encrypt recommended)
- Nginx installed on Proxmox host for reverse proxy

## Quick Deployment

### 1. Install Docker on Proxmox (if not already installed)

```bash
# Update system
apt update && apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh

# Install Docker Compose
apt install docker-compose -y

# Verify installation
docker --version
docker-compose --version
```

### 2. Clone/Upload Project to Proxmox

```bash
# Create directory
mkdir -p /opt/passport-photo-enhancer
cd /opt/passport-photo-enhancer

# Upload your project files here
# Or use git clone if you have a repository
```

### 3. Build and Start Containers

```bash
# Build and start services
docker-compose up -d --build

# Check status
docker-compose ps

# View logs
docker-compose logs -f
```

### 4. Configure Nginx Reverse Proxy

```bash
# Install Nginx (if not installed)
apt install nginx -y

# Copy the nginx configuration
cp nginx-proxy.conf /etc/nginx/sites-available/photo.qaam.work

# Create symbolic link
ln -s /etc/nginx/sites-available/photo.qaam.work /etc/nginx/sites-enabled/

# Test configuration
nginx -t

# Reload Nginx
systemctl reload nginx
```

### 5. Setup SSL with Let's Encrypt

```bash
# Install Certbot
apt install certbot python3-certbot-nginx -y

# Obtain SSL certificate
certbot --nginx -d photo.qaam.work

# Certbot will automatically configure SSL in Nginx
# Follow the prompts to complete setup

# Test auto-renewal
certbot renew --dry-run
```

## Alternative: Manual SSL Certificate Setup

If using custom SSL certificates, update the paths in `nginx-proxy.conf`:

```nginx
ssl_certificate /path/to/your/photo.qaam.work.crt;
ssl_certificate_key /path/to/your/photo.qaam.work.key;
```

## Docker Compose Configuration

The `docker-compose.yml` includes:

- **Backend Service**: FastAPI application on internal network
- **Frontend Service**: React app with Nginx, exposed on port 80
- **Health Checks**: Automatic container health monitoring
- **Auto-restart**: Containers restart on failure

### Environment Variables (Optional)

Create `.env` file in project root:

```env
# Backend settings
BACKEND_PORT=8000
PYTHONUNBUFFERED=1

# Frontend settings
FRONTEND_PORT=80
```

## Port Mapping

- **Container Port 80** → **Host Port 80** (HTTP)
- Backend runs internally on port 8000 (not exposed to host)
- Nginx on Proxmox host proxies HTTPS (443) to container port 80

## Useful Commands

### Container Management

```bash
# Start services
docker-compose up -d

# Stop services
docker-compose down

# Restart services
docker-compose restart

# View logs
docker-compose logs -f

# View specific service logs
docker-compose logs -f backend
docker-compose logs -f frontend

# Rebuild containers
docker-compose up -d --build

# Remove all containers and volumes
docker-compose down -v
```

### Monitoring

```bash
# Check container status
docker-compose ps

# Check resource usage
docker stats

# Check health status
docker inspect passport-photo-backend | grep -A 10 Health
docker inspect passport-photo-frontend | grep -A 10 Health
```

### Updates and Maintenance

```bash
# Pull latest changes (if using git)
git pull

# Rebuild and restart
docker-compose down
docker-compose up -d --build

# Clean up old images
docker image prune -a
```

## Firewall Configuration

Ensure ports are open on Proxmox:

```bash
# Allow HTTP
ufw allow 80/tcp

# Allow HTTPS
ufw allow 443/tcp

# Check status
ufw status
```

## Troubleshooting

### Container won't start

```bash
# Check logs
docker-compose logs

# Check individual service
docker-compose logs backend
docker-compose logs frontend
```

### Backend connection issues

```bash
# Test backend health
docker exec passport-photo-backend curl http://localhost:8000/

# Check network
docker network inspect passport-photo-network
```

### Frontend can't reach backend

```bash
# Verify both containers are on same network
docker-compose ps

# Check nginx config inside frontend container
docker exec passport-photo-frontend cat /etc/nginx/conf.d/default.conf
```

### SSL Certificate Issues

```bash
# Renew certificate manually
certbot renew

# Check certificate expiry
certbot certificates

# Test Nginx config
nginx -t
```

### High Memory Usage

```bash
# Check resource usage
docker stats

# Limit container resources (add to docker-compose.yml)
services:
  backend:
    deploy:
      resources:
        limits:
          cpus: '1'
          memory: 2G
```

## Performance Optimization

### 1. Enable Nginx Caching

Add to nginx-proxy.conf:

```nginx
proxy_cache_path /var/cache/nginx levels=1:2 keys_zone=my_cache:10m max_size=1g inactive=60m;

location / {
    proxy_cache my_cache;
    proxy_cache_valid 200 60m;
    # ... rest of config
}
```

### 2. Increase Worker Processes

Update backend Dockerfile CMD:

```dockerfile
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
```

## Backup Strategy

```bash
# Backup docker-compose and configs
tar -czf passport-photo-backup-$(date +%Y%m%d).tar.gz \
  docker-compose.yml \
  nginx-proxy.conf \
  backend/ \
  frontend/

# Restore from backup
tar -xzf passport-photo-backup-YYYYMMDD.tar.gz
```

## Security Checklist

- ✅ SSL/TLS enabled with valid certificate
- ✅ Firewall configured (only 80, 443 open)
- ✅ Regular updates (`apt update && apt upgrade`)
- ✅ Docker containers run as non-root (if needed)
- ✅ Security headers configured in Nginx
- ✅ File upload size limited (50MB)
- ✅ Auto-renewal for SSL certificates

## Monitoring and Logs

### Application Logs

```bash
# Real-time logs
docker-compose logs -f

# Last 100 lines
docker-compose logs --tail=100

# Logs for specific time
docker-compose logs --since 2h
```

### Nginx Logs

```bash
# Access logs
tail -f /var/log/nginx/photo.qaam.work.access.log

# Error logs
tail -f /var/log/nginx/photo.qaam.work.error.log
```

## Production Checklist

Before going live:

- [ ] Domain DNS configured correctly
- [ ] SSL certificate installed and auto-renewal working
- [ ] Firewall rules configured
- [ ] Docker containers running and healthy
- [ ] Nginx reverse proxy configured
- [ ] Test image upload and processing
- [ ] Monitor logs for errors
- [ ] Set up automated backups
- [ ] Document any custom configurations

## Support

For issues:
1. Check container logs: `docker-compose logs`
2. Verify network connectivity
3. Check Nginx configuration: `nginx -t`
4. Review SSL certificate status: `certbot certificates`

## Accessing the Application

Once deployed, access your application at:
- **HTTP**: `http://photo.qaam.work` (redirects to HTTPS)
- **HTTPS**: `https://photo.qaam.work`

The application will be available 24/7 with automatic restarts on failure.
