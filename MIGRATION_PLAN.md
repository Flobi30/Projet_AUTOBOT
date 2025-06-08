# AUTOBOT Production Migration Plan
## From Static Files to FastAPI Deployment

### Current Architecture
- **Production Server**: 144.76.16.177
- **Current Container**: autobot-simple (python:3.10-slim with basic pip install)
- **Nginx Config**: Multiple configs (autobot, autobot-static, autobot-standalone variants)
- **Current Deployment**: Static files served from /home/autobot/Projet_AUTOBOT/public/
- **No SSL**: No SSL certificates currently configured
- **No Volumes**: Current container has no persistent volumes

### Migration Strategy: Blue/Green Deployment

#### Phase 1: Backup and Preparation
1. ✅ Git tag created: `pre-fastapi-switch-20250608`
2. ✅ Backup scripts created: `deploy-production.sh backup`
3. ✅ Staging deployment script: `deploy-staging.sh`

#### Phase 2: Staging Environment
1. Build FastAPI Docker image with proper Dockerfile
2. Deploy to staging port 8001 with volume mounts:
   - `/home/autobot/Projet_AUTOBOT/data:/app/data`
   - `/home/autobot/Projet_AUTOBOT/logs:/app/logs`
   - `/home/autobot/Projet_AUTOBOT/config:/app/config`
3. Test authentication, LIVE badge, API persistence

#### Phase 3: Production Deployment
1. Stop current autobot-simple container
2. Disable static nginx configs (autobot-static, autobot-standalone*)
3. Enable FastAPI proxy config (autobot)
4. Start new FastAPI container with proper volumes
5. Verify functionality

#### Phase 4: Rollback Capability
- Rollback time target: < 1 minute
- Restore static nginx config
- Restart original container
- Verify static deployment works

### Smoke Tests Required
1. Login with credentials: AUTOBOT / 333333Aesnpr54& / AUTOBOT-eyJ0eXAi-OiJKV1Qi-LCJhbGci-OiJIUzUx
2. Verify LIVE AUTOMATION badge appears automatically
3. Confirm real-time logs stream in dashboard
4. Test API key persistence in Paramètres page
5. Verify no white sandwich button appears
6. Check responsive layout works correctly

### Risk Mitigation
- Complete backup before any changes
- Staging environment for testing
- Automated rollback script
- No SSL dependencies to break
- Volume mounts preserve data
