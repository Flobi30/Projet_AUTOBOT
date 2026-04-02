## MISSION: Review Sécurité & Architecture — Approfondie

Tu es expert sécurité. Fais une review approfondie de tout le projet post-push.

### Scope
Tous les fichiers dans src/autobot/v2/

### Checklist Approfondie

1. **Surface d'attaque**
   - Points d'entrée non protégés
   - Injection possible
   - Fuite de données

2. **Architecture**  
   - Single point of failure
   - Race conditions inter-modules
   - Deadlock potentiels

3. **Secrets & Credentials**
   - Clés API bien protégées
   - Pas de log de secrets
   - Rotation possible

4. **Robustesse**
   - Crash recovery
   - État cohérent après redémarrage
   - Gestion des erreurs cascade

5. **Production Readiness**
   - Health check
   - Monitoring
   - Alertes

### Livrables
- 🔴 CRITIQUE (bloquant production)
- 🟡 WARNING (risque élevé)
- 🟢 INFO (amélioration)
- Plan d'action priorisé
