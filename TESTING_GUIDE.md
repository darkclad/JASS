# Threaded Cover Letter Generation - Testing Guide

## Overview

This guide provides comprehensive testing procedures for the threaded cover letter generation feature. It includes unit tests, integration tests, performance tests, and troubleshooting procedures.

## Prerequisites

1. JASS application running
2. AI provider configured (Claude, OpenAI, Ollama, or Claude CLI)
3. Master resume created
4. At least one job saved

## Basic Functionality Tests

### Test 1: End-to-End Generation

**Purpose:** Verify complete document generation workflow

**Steps:**
1. Navigate to a saved job detail page
2. Click "Generate Resume & Cover Letter" button
3. Observe SSE progress updates
4. Verify redirect to application detail page
5. Check that both resume and cover letter PDFs are created

**Expected Results:**
- Progress updates appear in button text
- Generation completes without errors
- Both PDFs downloadable from application page
- Database updated with correct paths

**Verification:**
```bash
# Check application folder
ls "d:\Work\Programming\Jass\data\applications\{Company}_{JobId}"

# Should contain:
# - FirstName_LastName.md (resume markdown)
# - FirstName_LastName.pdf (resume PDF)
# - FirstName_LastName_cover.md (cover letter markdown)
# - FirstName_LastName_cover.pdf (cover letter PDF)
```

### Test 2: Parallel Execution Verification

**Purpose:** Confirm threads run in parallel

**Steps:**
1. Add timing logs to verify parallel execution
2. Generate documents for a job
3. Check logs for thread start times

**Code to Add (Temporary):**
```python
# In app.py, after line 906:
log.info(f"[TIMING] Resume PDF thread started at {datetime.utcnow()}")

# After line 907:
log.info(f"[TIMING] Cover letter thread started at {datetime.utcnow()}")
```

**Expected Results:**
- Both threads start within milliseconds of each other
- Log shows: `[Resume PDF Thread]` and `[CL Thread]` messages interleaved
- Total time < sequential time

**Log Example:**
```
[TIMING] Resume PDF thread started at 2026-02-09 10:15:30.123
[TIMING] Cover letter thread started at 2026-02-09 10:15:30.125
[Resume PDF Thread] Starting resume PDF generation
[CL Thread] Starting cover letter generation
[Resume PDF Thread] Resume PDF generation complete
[CL Thread] Cover letter generation complete
Both threads completed successfully, saving to database
```

### Test 3: Resume-Only Generation

**Purpose:** Verify resume-only generation still works

**Steps:**
1. Navigate to job detail page
2. Click "Generate Resume Only" button
3. Verify resume is created
4. Click "Generate Cover Letter Only" button
5. Verify cover letter is created

**Expected Results:**
- Resume generated successfully
- Cover letter generated successfully using existing resume
- Both PDFs created and downloadable

## Error Handling Tests

### Test 4: AI Provider Failure (Resume)

**Purpose:** Verify error handling when resume generation fails

**Setup:**
1. Configure AI provider with invalid API key
2. Attempt to generate documents

**Expected Results:**
- Error caught and logged
- SSE error event sent to client
- User sees error message
- No partial database update
- No files created

**Verification:**
```python
# Check logs for:
# Error in resume generation: [error message]
# No database commit should occur
```

### Test 5: AI Provider Failure (Cover Letter)

**Purpose:** Verify error handling when cover letter generation fails

**Setup:**
1. Modify `generate_cover_letter_threaded()` to simulate failure:
```python
# Add before line 1008 in app.py:
if job_id == 123:  # Replace with actual test job ID
    raise Exception("Simulated cover letter failure")
```

**Expected Results:**
- Resume PDF created successfully
- Cover letter thread returns error
- Error detected by main thread
- SSE error event sent
- No database update (transaction rolled back)

**Cleanup:** Remove simulated failure code

### Test 6: PDF Generation Failure

**Purpose:** Verify handling of md-to-pdf failures

**Setup:**
1. Temporarily rename md-to-pdf:
```bash
cd node_modules/.bin
mv md-to-pdf.cmd md-to-pdf.cmd.backup  # Windows
# or
mv md-to-pdf md-to-pdf.backup  # Linux/Mac
```

**Expected Results:**
- Markdown files created
- PDF generation fails
- Error logged
- SSE error event sent
- User informed of failure

**Cleanup:**
```bash
cd node_modules/.bin
mv md-to-pdf.cmd.backup md-to-pdf.cmd  # Windows
# or
mv md-to-pdf.backup md-to-pdf  # Linux/Mac
```

### Test 7: Thread Timeout

**Purpose:** Verify timeout handling

**Setup:**
1. Modify thread timeout to very short value:
```python
# In app.py, change line 925:
resume_pdf_thread.join(timeout=0.001)  # Changed from 5
```

**Expected Results:**
- Thread times out
- `queue.Empty` exception raised
- Error message: "Resume PDF generation thread did not return a result"
- SSE error sent to client

**Cleanup:** Restore timeout to 5 seconds

### Test 8: Database Connection Failure

**Purpose:** Verify handling of database errors

**Setup:**
1. Temporarily make database file read-only
2. Attempt generation

**Expected Results:**
- Documents generated successfully
- Database commit fails
- Error caught and logged
- User sees error message

**Cleanup:** Restore database permissions

## Performance Tests

### Test 9: Timing Comparison

**Purpose:** Measure performance improvement

**Setup:**
1. Create timing test script
2. Generate 10 applications sequentially (without threading)
3. Generate 10 applications with threading
4. Compare average times

**Test Script:**
```python
import time
import requests
import statistics

BASE_URL = "http://localhost:5000"
JOB_ID = 123  # Replace with actual job ID

def test_generation_time(job_id, num_runs=10):
    times = []

    for i in range(num_runs):
        start = time.time()

        # Trigger generation via SSE endpoint
        response = requests.get(
            f"{BASE_URL}/jobs/{job_id}/tailor-stream",
            stream=True
        )

        # Read all SSE events until completion
        for line in response.iter_lines():
            if b'Complete!' in line or b'error' in line:
                break

        elapsed = time.time() - start
        times.append(elapsed)
        print(f"Run {i+1}: {elapsed:.2f}s")

        # Clean up (delete application)
        # ... cleanup code ...

    print(f"\nResults over {num_runs} runs:")
    print(f"  Average: {statistics.mean(times):.2f}s")
    print(f"  Median: {statistics.median(times):.2f}s")
    print(f"  Std Dev: {statistics.stdev(times):.2f}s")
    print(f"  Min: {min(times):.2f}s")
    print(f"  Max: {max(times):.2f}s")

test_generation_time(JOB_ID)
```

**Expected Results:**
- Threaded version 15-30% faster on average
- More consistent timing (lower std dev)

### Test 10: Memory Usage

**Purpose:** Monitor memory consumption

**Setup:**
1. Use memory profiling tool
2. Generate multiple documents concurrently

**Linux/Mac:**
```bash
# Monitor Python process memory
ps aux | grep python | grep app.py

# Or use top
top -p $(pgrep -f "python.*app.py")
```

**Windows:**
```powershell
# Monitor in Task Manager
# Or use PowerShell:
Get-Process python | Select-Object ProcessName, WorkingSet
```

**Expected Results:**
- Memory increases during generation
- Memory released after completion
- No memory leaks over multiple generations

### Test 11: Concurrent Requests

**Purpose:** Test system under concurrent load

**Test Script:**
```python
import concurrent.futures
import requests

def generate_for_job(job_id):
    response = requests.get(
        f"http://localhost:5000/jobs/{job_id}/tailor-stream",
        stream=True
    )
    for line in response.iter_lines():
        if b'Complete!' in line or b'error' in line:
            return True
    return False

# Test with 5 concurrent requests
job_ids = [1, 2, 3, 4, 5]  # Replace with actual job IDs

with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
    futures = [executor.submit(generate_for_job, jid) for jid in job_ids]
    results = [f.result() for f in concurrent.futures.as_completed(futures)]

print(f"Success rate: {sum(results)}/{len(results)}")
```

**Expected Results:**
- All requests complete successfully
- No database conflicts
- No file path conflicts
- Acceptable response time

## Integration Tests

### Test 12: All AI Providers

**Purpose:** Verify threading works with all AI providers

**Test Matrix:**

| Provider | Resume | Cover Letter | Status |
|----------|--------|--------------|--------|
| Claude API | ✓ | ✓ | Pass/Fail |
| OpenAI API | ✓ | ✓ | Pass/Fail |
| Ollama | ✓ | ✓ | Pass/Fail |
| Claude CLI | ✓ | ✓ | Pass/Fail |

**Steps for Each:**
1. Configure AI provider in settings
2. Test AI connection
3. Generate resume and cover letter
4. Verify both documents created

### Test 13: Different Job Types

**Purpose:** Test with various job descriptions

**Test Cases:**
1. **Short job description** (< 500 chars)
2. **Medium job description** (500-2000 chars)
3. **Long job description** (> 2000 chars)
4. **HTML job description** (from Greenhouse)
5. **Plain text job description** (manual entry)

**Expected Results:**
- All job types generate successfully
- Cover letter quality appropriate to description length
- No parsing errors

### Test 14: Edge Cases

**Purpose:** Test boundary conditions

**Test Cases:**

1. **Empty hiring manager:**
   - Job with no hiring manager specified
   - Cover letter should not reference manager

2. **Special characters in company name:**
   - Company: "O'Reilly Media, Inc."
   - Folder: `O_Reilly_Media_Inc_123`
   - Files created successfully

3. **Very long company name:**
   - Company: 200 character name
   - Folder name sanitized correctly
   - No file system errors

4. **Unicode in job description:**
   - Description with emoji, accents, etc.
   - AI handles correctly
   - PDF renders properly

## Regression Tests

### Test 15: Backward Compatibility

**Purpose:** Ensure existing features still work

**Checklist:**
- ✓ Job search functionality
- ✓ Manual job addition
- ✓ Master resume editing
- ✓ Application editing
- ✓ Document download
- ✓ Application deletion
- ✓ Settings configuration
- ✓ AI chat feature

### Test 16: Database Integrity

**Purpose:** Verify database consistency

**Queries:**
```sql
-- Check all applications have valid paths
SELECT id, job_id, resume_md, resume_pdf, cover_letter_md, cover_letter_pdf
FROM application
WHERE resume_md IS NULL OR resume_pdf IS NULL
   OR cover_letter_md IS NULL OR cover_letter_pdf IS NULL;

-- Verify files exist
-- (Run Python script to check file paths)
```

**Python Script:**
```python
from models import Application, db
from app import app
import os

with app.app_context():
    apps = Application.query.all()
    missing_files = []

    for app_obj in apps:
        paths = [
            app_obj.resume_md,
            app_obj.resume_pdf,
            app_obj.cover_letter_md,
            app_obj.cover_letter_pdf
        ]

        for path in paths:
            if path and not os.path.exists(path):
                missing_files.append({
                    'app_id': app_obj.id,
                    'path': path
                })

    if missing_files:
        print(f"Found {len(missing_files)} missing files:")
        for mf in missing_files:
            print(f"  App {mf['app_id']}: {mf['path']}")
    else:
        print("All files present!")
```

## Troubleshooting Tests

### Test 17: Log Analysis

**Purpose:** Verify comprehensive logging

**Check Logs For:**

1. **Thread lifecycle:**
   ```
   Started parallel threads for resume PDF and cover letter generation
   [Resume PDF Thread] Starting resume PDF generation
   [Resume PDF Thread] Resume PDF generation complete
   Both threads completed successfully, saving to database
   ```

2. **Error handling:**
   ```
   [Resume PDF Thread] Error: [error message]
   Error generating documents: [error message]
   ```

3. **Timing information:**
   ```
   Resume markdown generated: 1234 chars
   Cover letter generation completed for job 123
   Documents saved successfully for application 456
   ```

### Test 18: SSE Event Verification

**Purpose:** Verify all SSE events are sent

**Client-Side Test:**
```javascript
const eventSource = new EventSource('/jobs/123/tailor-stream');
const events = [];

eventSource.onmessage = (event) => {
    const data = JSON.parse(event.data);
    events.push(data);
    console.log('Event:', data);
};

eventSource.onerror = (error) => {
    console.error('SSE Error:', error);
    eventSource.close();
};

// After completion, verify events array contains all expected events
```

**Expected Events:**
1. `{status: "Initializing AI..."}`
2. `{status: "Tailoring resume..."}`
3. `{status: "Generating PDFs and cover letter..."}`
4. `{status: "Generating cover letter..."}`
5. `{status: "Generating cover letter PDF..."}`
6. `{status: "Cover letter complete!"}`
7. `{status: "Complete!", redirect: "/applications/123"}`

## Performance Benchmarks

### Baseline Metrics (Pre-Threading)

| Metric | Value |
|--------|-------|
| Average generation time | ~30s |
| Memory usage | ~100MB |
| CPU usage | ~25% |

### Target Metrics (Post-Threading)

| Metric | Target | Actual |
|--------|--------|--------|
| Average generation time | < 25s | ___s |
| Memory usage | < 165MB | ___MB |
| CPU usage | < 40% | ___% |
| Success rate | > 99% | ___% |

## Automation Script

Complete automated test suite:

```bash
#!/bin/bash
# automated_test_suite.sh

echo "Starting JASS Threading Tests..."
echo "================================"

# Test 1: Syntax validation
echo "Test 1: Syntax validation"
python -c "import ast; ast.parse(open('app.py').read())" && echo "PASS" || echo "FAIL"

# Test 2: Basic generation
echo "Test 2: Basic generation"
curl -s "http://localhost:5000/jobs/1/tailor-stream" | grep -q "Complete" && echo "PASS" || echo "FAIL"

# Test 3: Error handling (invalid job ID)
echo "Test 3: Error handling"
curl -s "http://localhost:5000/jobs/99999/tailor-stream" | grep -q "error" && echo "PASS" || echo "FAIL"

# Test 4: File creation
echo "Test 4: File creation"
test -f "data/applications/*/FirstName_LastName.pdf" && echo "PASS" || echo "FAIL"

# Test 5: Database update
echo "Test 5: Database update"
python -c "
from app import app
from models import Application, db
with app.app_context():
    app = Application.query.first()
    assert app.resume_pdf is not None
    assert app.cover_letter_pdf is not None
    print('PASS')
"

echo "================================"
echo "Tests complete!"
```

## Continuous Integration

Add to CI/CD pipeline:

```yaml
# .github/workflows/test.yml
name: JASS Threading Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest

    steps:
    - uses: actions/checkout@v2

    - name: Set up Python
      uses: actions/setup-python@v2
      with:
        python-version: '3.10'

    - name: Install dependencies
      run: |
        pip install -r requirements.txt
        npm install md-to-pdf

    - name: Run tests
      run: |
        python -m pytest tests/test_threading.py -v

    - name: Check syntax
      run: |
        python -c "import ast; ast.parse(open('app.py').read())"
```

## Conclusion

This testing guide covers:
- ✓ Basic functionality
- ✓ Error handling
- ✓ Performance
- ✓ Integration
- ✓ Regression
- ✓ Troubleshooting

Follow this guide to ensure the threaded cover letter generation feature works correctly and performs as expected.
