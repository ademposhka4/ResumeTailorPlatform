# MyApply Resume Tailor

This is the class project where I'm building a lightweight resume tailoring portal on top of Django. Job seekers can track roles they're interested in, store a structured "experience graph," and run a staged OpenAI workflow that builds job profiles, selects experience snippets, and returns guardrail-checked resume bullets. Everything runs against MySQL and Django-Q background workers so the browser never blocks while OpenAI does its thing.

## What lives in each app?

- **accounts** – custom `User` model with roles plus token/word usage counters so I can rate-limit OpenAI consumption.
- **profiles** – simple CRUD for the user’s personal info and links that end up on the resume preview.
- **experience** – the “experience graph” manager. Users edit job, project, education, and volunteer entries through well-validated forms that write to JSON in MySQL. Sorting, validation, and conversions all live in `experience/services.py`.
- **jobs** – lets a user paste a job description, drop a posting URL, or do both. Stores parsing metadata so the tailoring service can reuse it.
- **tailoring** – asynchronous pipeline: snapshots the job + experience data, enqueues a Django-Q task, calls the OpenAI Responses API, and stores the generated bullets/sections/suggestions with debug logs.
- **maps** – placeholder for Mapbox commute calculations (API key wiring is already in settings but the feature is still a stub).
- **myapply** – the project config plus shared templates (`base.html`, dashboard, login) and Django-Q configuration.

## Stack + infrastructure

- **Backend**: Django 4.2, Python 3.10+, Django REST Framework for the API, **Django-Q2** for background task processing (uses MySQL as queue backend).
- **Database**: MySQL only. There's no SQLite fallback anywhere, so make sure you have a running MySQL 8 instance for dev and tests.
- **AI**: OpenAI **Responses API** (model defaults to `gpt-4o-mini`). The tailoring service uses the Responses API with conditional JSON mode for reliable structured output. It builds job profiles, scores experience snippets, orchestrates staged generation + guardrail passes, and records token usage per call. Web search tool integration enables automatic job posting fetching from URLs and location coordinate extraction.
- **Background Tasks**: Django-Q2 with MySQL ORM backend (no Redis or external broker required). This works seamlessly on PythonAnywhere and other hosting platforms.
- **Other services**: Optional Mapbox token waiting for the maps feature.
- **Frontend**: Django template system with all templates scoped to each app, plus a shared CSS file in `static/css/style.css`.

## Local setup

1. Clone the repo and create a virtualenv.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Make sure MySQL is running and create a database/user. For example:
   ```sql
   CREATE DATABASE myapply CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
   CREATE USER 'myapply_user'@'localhost' IDENTIFIED BY 'choose_a_password';
   GRANT ALL PRIVILEGES ON myapply.* TO 'myapply_user'@'localhost';
   FLUSH PRIVILEGES;
   ```
4. Copy `.env.example` to `.env` and fill in the blanks for `DJANGO_SECRET_KEY`, MySQL creds, `OPENAI_API_KEY`, and `OPENAI_MODEL`. No Redis or broker URLs needed anymore.
5. Run migrations:
   ```bash
   python manage.py migrate
   python manage.py createsuperuser
   ```
   ```bash
   python manage.py migrate
   python manage.py createsuperuser
   ```

6. In separate terminals, launch the Django-Q worker and Django dev server:
   ```bash
   # Terminal 1: Start Django-Q worker cluster
   python manage.py qcluster
   
   # Terminal 2: Start Django development server
   python manage.py runserver
   ```
7. Visit `http://127.0.0.1:8000/`, log in, and you're set.

**Note**: Django-Q stores tasks in the MySQL database, so no external services (like Redis) are required. The worker cluster processes tasks asynchronously and can be monitored via the Django admin interface at `/admin/django_q/`.

### Running tests

Tests expect a reachable MySQL database and any required env vars. Run everything with:
```bash
python manage.py test
```

## Feature highlights

### Experience manager
- Four supported types (work, education, project, volunteer) with validation baked into `ExperienceService`.
- Glassmorphism card UI, dynamic achievements, and comma-separated skill tags.
- Everything saved to the `ExperienceGraph` JSON field, sorted and sanitized before it touches MySQL.
- When a location is provided (and `MAPBOX_TOKEN` is set) the service forward-geocodes it with Mapbox and stores latitude/longitude for future isochrone calculations.

### Job tracking
- Single form that accepts a posting URL, raw description text, or both.
- Metadata fields (company, location, parsed_requirements, etc.) live on the `JobPosting` model, so the tailoring task can reuse them without re-scraping.
- **Visual Relationship Dashboard**: Each job card shows connected tailoring sessions with real-time status indicators
- **Session Analytics**: Track completion rates, token usage, and success metrics per job
- **Timeline Visualization**: View chronological history of all tailoring attempts for each job
- **Quick Actions**: Create new tailoring sessions directly from job cards with one click

### Tailoring workflow
- Creates a `TailoringSession` with snapshots of the job data and the user's experience graph, plus the exact tailoring parameters supplied by the UI/API.
- Normalizes those parameters (sections, tone, bullet counts, stretch level, cover-letter inserts) and builds a compact job profile with requirement buckets.
- Scores every experience/leadership/project node in the graph, trims to the top snippets per bucket, and sends summaries—never the raw wall of text—to OpenAI.
- **Staged OpenAI Responses API calls** (using JSON mode):
  1. **Resume generation** – Uses the Responses API with `text.format` set to `json_object` for reliable structured output. When a job URL is provided, the `web_search` tool fetches the complete posting. Returns sectioned bullets tied to snippet IDs with self-reported stretch metadata. Also extracts job location with approximate latitude/longitude coordinates.
  2. **Guardrail audit** – Replays each bullet against the source snippet and stretch policy with JSON mode enabled; only the lines that fail get regenerated.
  3. **Cover letter (optional)** – Produces a three-paragraph letter that reuses the same snippets plus any user-supplied talking points, also in JSON mode.
- All OpenAI calls use the **Responses API** (`/v1/responses`) with `text.format.type = "json_object"` to ensure valid JSON output without markdown wrapping or formatting issues.
- ATS scoring and bullet quality checks still run locally so every session comes with a keyword report and metric reminders.
- Guardrail findings, bullet details, section layout, cover-letter talking points, job location data, and token usage for every call live in `TailoringSession.output_metadata`.
- Token usage and word counts are recorded back onto the user for quota tracking.
- Session detail pages surface statuses, run IDs, guardrail notes, token stats, ATS scores, generated content, and a collapsible debug log for troubleshooting.

### Dashboard + profiles
- Dashboard pulls recent jobs, tailoring sessions, and token counts.
- Profile editor keeps basic resume contact info in sync with what the tailoring output expects.

### API surface
- REST endpoints for authentication, experience graph CRUD, job postings, tailoring sessions, and profiles (see `myapply/urls.py` + app `frontend_urls.py`).
- Token auth + session auth are both enabled so the web UI and API clients can coexist.

## Environment variables cheat sheet

```
DJANGO_SECRET_KEY=change-me
DEBUG=True
DB_NAME=myapply
DB_USER=myapply_user
DB_PASSWORD=...
DB_HOST=localhost
DB_PORT=3306
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
TAILORING_PENDING_TIMEOUT_MINUTES=5
TAILORING_PROCESSING_TIMEOUT_MINUTES=15
MAPBOX_TOKEN=optional
LOG_LEVEL=INFO
```

**Note:** Redis/Celery environment variables are no longer needed. Django-Q uses the MySQL database for task queuing.

## Why no SQLite?

The project relies on JSON columns, MySQL-specific ordering, and Django-Q background tasks that use the ORM. Tests and dev use the same MySQL instance so that I don't get surprised by behavior differences later. If MySQL isn't available, the app just won't boot.

## ATS + guardrail toolkit

- **Keyword + requirement extraction**: pulls skills, verbs, certifications, experience, and education into dedicated buckets so both ATS scoring and snippet matching reuse the same data set.
- **ATS scoring**: weighs required skills, overall keyword coverage, and preferred skills to produce the percentage that shows up in the UI.
- **Bullet validator**: checks action verbs, length, and metrics before surfacing suggestions back to the user.
- **Stretch guardrails**: OpenAI double-checks every bullet against the original snippet, applies the requested stretch policy (0–3), and regenerates only what fails.
- **Token tracking**: prompt/completion totals from every OpenAI call are merged and stored with the session for quota awareness.

### Using the System

#### For Job Seekers

**Target ATS Score: 85%+**

1. **Complete Your Experience Graph**
   - Add all relevant skills (system matches top 5 automatically)
   - Include metrics in achievements (%, $, numbers)
   - Use industry-standard terminology

2. **Provide Job URL or Description**
   - URL preferred (OpenAI fetches complete posting)
   - Include full description if pasting manually

3. **Review ATS Score**
   - Check the score at top of suggestions
   - Address missing required skills immediately
   - Add suggested keywords naturally

4. **Iterate Based on Suggestions**
   - Focus on required skills first (60% of score)
   - Add metrics where suggested
   - Ensure bullets start with action verbs

#### Example ATS Score Output
```
📊 ATS Compatibility: 87.3% | Required Skills: 93.3% | Keywords: 82.5%
```

**Suggestions Generated:**
- "CRITICAL: Add these required skills: Kubernetes, GraphQL"
- "Add quantifiable metrics (%, $, numbers)"
- "Excellent ATS compatibility! Your resume should pass most ATS filters."

## Technical Implementation

### Architecture

**Service layer (`tailoring/services.py`)**
- `run_workflow()` orchestrates everything: job profiling, snippet selection, staged OpenAI calls with JSON mode, and ATS analysis.
- `_build_job_profile()` distills the job description into requirement buckets for later reuse.
- `_collect_experience_snippets()` scores experience/leadership/project nodes and returns compact summaries.
- `_generate_resume_package()` calls OpenAI Responses API with `text.format.type = "json_object"`, runs guardrails/regeneration, and aggregates token usage.
- `_call_openai_json()` constructs the Responses API request with JSON mode enabled to ensure valid, parseable output without markdown wrapping.
- `_apply_guardrails()` and `_regenerate_bullets()` enforce the stretch policy before anything is saved.

**Background task (`tailoring/tasks.py`)**
- `process_tailoring_session()` locks the session, grabs the latest experience graph, normalizes parameters, and invokes the service.
- Persists generated sections, suggestions, cover letter, token stats, guardrail findings, and talking points back onto the session.

**Stored metadata**
`TailoringSession.output_metadata` now holds:
- `bullet_details` – snippet IDs, stretch levels, and metrics for every bullet.
- `guardrails` – status + reason codes for any audited bullet.
- `section_layout` – the normalized sections used during generation.
- `cover_letter_talking_points` – short highlights surfaced to the UI.

### Testing

#### Unit Tests
```bash
# Run all tests
python manage.py test

# Test specific module
python manage.py test tailoring.tests.test_services
```

#### Manual Testing
```bash
# Start development server
python manage.py runserver

# Start Django-Q worker cluster
python manage.py qcluster

# Create test session via admin or API
# Monitor Django-Q admin at /admin/django_q/ for task status
```

#### Validation Checklist
- [ ] OpenAI grounding fetches job posting correctly
- [ ] ATS score calculated accurately (85%+ target)
- [ ] Required skills coverage ≥90%
- [ ] 80%+ bullets have quantifiable metrics
- [ ] All bullets start with action verbs
- [ ] Bullet length between 100-180 characters
- [ ] Token usage optimized (<5,000 per session)

### Best Practices

#### For Developers

1. **Always Use JSON Mode for Responses API**
   - Set `text.format.type = "json_object"` in all OpenAI Responses API calls
   - This prevents markdown wrapping and malformed JSON issues
   - Never rely on the model to voluntarily format JSON correctly

2. **Use Web Search Tool for URLs**
   - More reliable than custom scraping
   - Handles dynamic content automatically
   - Reduces maintenance overhead
   - Enable by adding `{"type": "web_search"}` to the `tools` array

3. **Monitor Token Usage**
   - Current average: ~4,400 tokens/session
   - Alert if sessions exceed 7,000 tokens
   - Optimize prompts when possible

4. **ATS Score Thresholds**
   - Block submissions <50% (warn user)
   - Suggest improvements for 50-84%
   - Approve 85%+ automatically

5. **Error Handling**
   - Graceful fallback if OpenAI returns errors
   - Log all API errors with payload previews for debugging
   - Provide clear user feedback
   - JSON parsing errors now include line/column numbers and preview

6. **Keyword Maintenance**
   - Update keyword lists quarterly
   - Add emerging technologies (e.g., new frameworks)
   - Remove deprecated terms

#### For System Administrators

**Configuration Settings:**
```python
# settings.py
OPENAI_API_KEY = env('OPENAI_API_KEY')
OPENAI_MODEL = 'gpt-4o-mini'
OPENAI_TEMPERATURE = 0.7
OPENAI_MAX_TOKENS = 2000

Q_CLUSTER = {
    'name': 'myapply',
    'timeout': 600,
    'retry': 1200,
    'orm': 'default',  # Uses MySQL database as task queue
}

ATS_SCORE_THRESHOLD = 85  # Target score
ATS_CRITICAL_THRESHOLD = 50  # Minimum acceptable
```

**Monitoring:**
- Track ATS score distribution (aim for 85%+ average)
- Monitor OpenAI API latency and errors
- Alert on Django-Q task failures (check admin dashboard)
- Review token usage trends monthly

**Scaling Considerations:**
- MySQL database for task queue (handles thousands of tasks/hour)
- Add more `qcluster` workers for horizontal scaling
- OpenAI rate limits: 10,000 RPM (adjust if needed)
- Monitor Django-Q admin dashboard for task backlog

## Troubleshooting

### Common Issues

**Issue: Tasks Not Processing**
- **Symptoms**: Sessions stuck in "pending" status
- **Cause**: Django-Q worker (`qcluster`) is not running
- **Fix**: 
  ```bash
  # Start the worker cluster
  python manage.py qcluster
  
  # Or check if it's running
  ps aux | grep qcluster
  ```
- **Validation**: Check Django admin at `/admin/django_q/task/` to see task queue

**Issue: JSON Parsing Errors from OpenAI**
- **Cause**: Model returns unstructured text when web_search tool is used
- **Fix**: The code conditionally enables JSON mode - when web_search is needed, explicit instructions ensure JSON output
- **Validation**: Check logs for "Failed to parse OpenAI JSON payload" with line/column error details

**Issue: Low ATS Score (<70%)**
- **Cause**: Missing required skills or keywords
- **Fix**: Review "missing_required_skills" in ats_metadata, update experience graph

**Issue: OpenAI API Timeout**
- **Cause**: Large job descriptions or slow web search
- **Fix**: Increase timeout in Q_CLUSTER settings (`timeout` parameter), check OpenAI status

**Issue: No Metrics in Bullets**
- **Cause**: Experience graph lacks quantifiable achievements
- **Fix**: Add metrics to achievements (%, $, time saved), re-run session

**Issue: Task Stuck in 'processing'**
- **Cause**: Worker crashed or task timeout
- **Fix**: Check Django-Q logs in admin, restart qcluster, increase timeout in Q_CLUSTER settings

### Debug Commands

```bash
# Check Django-Q worker status
python manage.py qcluster --help

# View task details in Django admin
# Navigate to: /admin/django_q/task/

# Or check via shell
python manage.py shell
>>> from django_q.models import Task
>>> Task.objects.filter(name='tailoring.tasks.process_tailoring_session').order_by('-started')[:10]

# View specific session
>>> from tailoring.models import TailoringSession
>>> session = TailoringSession.objects.get(id=123)
>>> print(session.debug_log)
>>> print(session.status)

# Manually trigger a task (for testing)
>>> from django_q.tasks import async_task
>>> async_task('tailoring.tasks.process_tailoring_session', 123)
```

## Recent Updates

**November 2025 - Migration from Celery+Redis to Django-Q**
- **✅ Replaced Celery with Django-Q2**: Simplified background task processing
  - **No Redis required**: Django-Q uses MySQL database as queue backend
  - **PythonAnywhere compatible**: Works on any hosting platform with database access
  - **Simpler setup**: No external services, no separate broker configuration
  - **Built-in monitoring**: View task status in Django admin at `/admin/django_q/`
  - **Same features**: Async tasks, retries, timeouts all supported
  
- **Migration Benefits**:
  - Removed 2 dependencies: `celery` and `redis`
  - Reduced complexity: No Redis installation/management needed
  - Better portability: Deploy anywhere Django can run
  - Native Django integration: Uses ORM, migrations, admin interface

- **OpenAI API Fix**: Resolved incompatibility between `web_search` tool and JSON mode
  - OpenAI doesn't allow `web_search` with `text.format.type = "json_object"` simultaneously (returns 400 error)
  - Solution: Conditionally enable JSON mode only when web_search is NOT needed
  - When using web_search for job URL fetching, rely on explicit instructions for pure JSON output
  - Enhanced error logging to show line/column numbers and payload previews for debugging

## Deployment Notes

### PythonAnywhere Hosting

**✅ Now Fully Compatible with PythonAnywhere!**

The migration to Django-Q means this application now works seamlessly on PythonAnywhere and any other platform:

1. **Setup Django-Q Worker on PythonAnywhere:**
   - Go to Tasks tab → "Always-on tasks" section
   - Command: `source /path/to/venv/bin/activate && python manage.py qcluster`
   - This runs the Django-Q worker cluster continuously
   - See: https://help.pythonanywhere.com/pages/AlwaysOnTasks

2. **Monitor Tasks:**
   - Access Django admin: `https://yoursite.pythonanywhere.com/admin/`
   - Navigate to "Django Q" → "Tasks" to see task status
   - View successful, failed, and scheduled tasks
   - Check task logs and execution history

3. **Fallback Mechanism** (Already Implemented)
   - If Django-Q worker isn't running, tasks execute synchronously
   - The codebase has a fallback in `tailoring/frontend_views.py`
   - This works but blocks the web request (not ideal for production)
   - Always run `qcluster` for best performance

**For Other Hosting Providers:**
- **Heroku**: Add worker dyno with `python manage.py qcluster` command
- **DigitalOcean**: Run qcluster as systemd service
- **AWS/Google Cloud**: Deploy qcluster in container or EC2/Compute Engine instance
- **Any VPS**: Use supervisor or systemd to keep qcluster running

No Redis, no external brokers, no complexity - just Django and MySQL.

## Old scripts & docs

Everything that used to live in `EXPERIENCE_FEATURE.md` is folded into this README. The legacy shell test `test_experience_service.py` has been dropped now that automated tests cover the service layer.
