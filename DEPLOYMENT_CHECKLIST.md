# Production Deployment Checklist

## Pre-Deployment

✅ **Code Changes:**
- [x] OpenAI integration added
- [x] Token counting implemented
- [x] Cost tracking implemented
- [x] Async task status endpoint added
- [x] Migration file created

✅ **Configuration:**
- [x] `.do/app.yaml` updated with `OPENAI_API_KEY` and `OPENAI_MODEL`
- [x] `requirements.txt` updated with `openai` and `tiktoken`
- [x] Settings configured for OpenAI

## Deployment Steps

### 1. Commit Changes
```bash
git add .
git commit -m "feat: Add OpenAI integration with token counting and cost tracking"
```

### 2. Push to Production Branch
```bash
# If deploying from develop branch
git checkout prod
git merge develop
git push origin prod

# OR if already on prod branch
git push origin prod
```

### 3. Set Environment Variables in Digital Ocean

**CRITICAL:** After deployment, set `OPENAI_API_KEY` in Digital Ocean:

1. Go to Digital Ocean App Platform
2. Navigate to your app → Settings → App-Level Environment Variables
3. Add/Update:
   - `OPENAI_API_KEY` (type: SECRET) - Your OpenAI API key
   - `OPENAI_MODEL` (optional, defaults to "gpt-4o-mini")

### 4. Verify Deployment

After deployment completes:
1. Check app logs for migration success
2. Test creating a dietary goal
3. Verify Celery worker is processing tasks
4. Check that OpenAI API calls are working

## Post-Deployment

- [ ] Verify migrations ran successfully
- [ ] Test creating a dietary goal
- [ ] Verify task status endpoint works
- [ ] Check cost tracking in API responses
- [ ] Monitor Celery worker logs

## Rollback Plan

If issues occur:
```bash
git revert <commit-hash>
git push origin prod
```

## Notes

- Migration will run automatically via `start.sh`
- Celery worker should start automatically
- OpenAI API key must be set as SECRET in Digital Ocean
- Default model: `gpt-4o-mini` (cost-effective)



