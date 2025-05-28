# AUTOBOT Deployment Guide

This guide provides instructions for deploying AUTOBOT in various environments, from development to production.

## Prerequisites

Before deploying AUTOBOT, ensure you have the following prerequisites installed:

- Docker and Docker Compose
- Git
- Python 3.10 or higher (for local development)
- Node.js 16 or higher (for frontend development)

## Development Environment

### Local Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/Flobi30/Projet_AUTOBOT.git
   cd Projet_AUTOBOT
   ```

2. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -e .
   pip install -r requirements.txt
   pip install -r requirements.dev.txt
   ```

4. Set up environment variables:
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

5. Run the application:
   ```bash
   uvicorn src.autobot.main:app --reload
   ```

6. Access the application at http://localhost:8000

### Docker Development

1. Build and run the Docker containers:
   ```bash
   docker-compose -f docker-compose.dev.yml up --build
   ```

2. Access the application at http://localhost:8000

## Production Deployment

### Docker Deployment

1. Configure environment variables:
   ```bash
   cp .env.example .env.prod
   # Edit .env.prod with production configuration
   ```

2. Build and run the production containers:
   ```bash
   docker-compose --env-file .env.prod up -d
   ```

3. Access the application at http://your-server-ip:8000

### Kubernetes Deployment

1. Apply Kubernetes manifests:
   ```bash
   kubectl apply -f k8s/
   ```

2. Configure ingress or load balancer as needed.

## Configuration Options

AUTOBOT can be configured using environment variables or a configuration file. The following options are available:

### Environment Variables

- `ENVIRONMENT`: Set to `development`, `staging`, or `production`
- `LOG_LEVEL`: Set to `debug`, `info`, `warning`, or `error`
- `DATABASE_URL`: Database connection string
- `JWT_SECRET`: Secret key for JWT token generation
- `ENABLE_DOCS`: Set to `true` to enable API documentation
- `TRADING_EXCHANGES`: Comma-separated list of enabled exchanges
- `RL_TRAINING_ENABLED`: Set to `true` to enable RL training

### Configuration File

You can also use a configuration file by setting the `CONFIG_FILE` environment variable:

```bash
export CONFIG_FILE=/path/to/config.yaml
```

Example configuration file:

```yaml
environment: production
log_level: info
database:
  url: sqlite:///data/autobot.db
security:
  jwt_secret: your-secret-key
  enable_docs: false
trading:
  exchanges:
    - binance
    - coinbase
    - kraken
  default_exchange: binance
rl:
  training_enabled: true
  model_dir: /data/models
```

## Scaling

AUTOBOT can be scaled horizontally to handle increased load:

1. Scale the API server:
   ```bash
   docker-compose up -d --scale autobot=3
   ```

2. Use a load balancer (e.g., Nginx, HAProxy) to distribute traffic.

3. Scale the worker processes based on workload:
   ```bash
   docker-compose up -d --scale autobot-worker=5
   ```

## Monitoring

Monitor your AUTOBOT deployment using:

1. Built-in monitoring dashboard at http://your-server-ip:8000/performance

2. Prometheus metrics at http://your-server-ip:8000/metrics

3. Health check endpoint at http://your-server-ip:8000/health

## Backup and Recovery

1. Back up the data directory regularly:
   ```bash
   tar -czf autobot-data-backup-$(date +%Y%m%d).tar.gz data/
   ```

2. Back up the database:
   ```bash
   # For SQLite
   cp data/autobot.db data/autobot.db.backup
   
   # For PostgreSQL
   pg_dump -U username -d autobot > autobot-db-backup-$(date +%Y%m%d).sql
   ```

3. To restore from backup:
   ```bash
   # Restore data directory
   tar -xzf autobot-data-backup-20230101.tar.gz
   
   # Restore SQLite database
   cp data/autobot.db.backup data/autobot.db
   
   # Restore PostgreSQL database
   psql -U username -d autobot < autobot-db-backup-20230101.sql
   ```

## Troubleshooting

### Common Issues

1. **Container fails to start**:
   - Check logs: `docker-compose logs autobot`
   - Verify environment variables are set correctly
   - Ensure database connection is valid

2. **API returns 500 errors**:
   - Check application logs: `docker-compose logs autobot`
   - Verify database migrations have been applied
   - Check for permission issues on data directories

3. **Worker processes not running**:
   - Check worker logs: `docker-compose logs autobot-worker`
   - Verify message queue connection
   - Check for resource constraints

### Getting Help

If you encounter issues not covered in this guide:

1. Check the [GitHub Issues](https://github.com/Flobi30/Projet_AUTOBOT/issues) for similar problems
2. Review the [FAQ](./FAQ.md) for common questions
3. Open a new issue with detailed information about your problem
