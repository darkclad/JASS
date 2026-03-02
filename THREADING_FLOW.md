# Cover Letter Threading Flow Diagram

## High-Level Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Main Thread (SSE)                            │
└─────────────────────────────────────────────────────────────────────┘
    │
    ├─ 1. Initialize AI provider
    │
    ├─ 2. Generate resume markdown (BLOCKING - needed by cover letter)
    │     ↓
    │     [tailored_resume markdown text ready]
    │
    ├─ 3. Start parallel threads:
    │     │
    │     ├──────────────────────────┬─────────────────────────────────┐
    │     │                          │                                 │
    │     ▼                          ▼                                 ▼
    │  ┌─────────────────┐    ┌──────────────────┐    ┌──────────────────────┐
    │  │ Resume PDF      │    │ Cover Letter     │    │ Event Stream         │
    │  │ Thread          │    │ Thread           │    │ (to client)          │
    │  └─────────────────┘    └──────────────────┘    └──────────────────────┘
    │     │                          │                         │
    │     │ - Save resume MD         │ - Get AI provider       │ - "Generating
    │     │ - Generate PDF           │ - Generate CL MD        │    PDFs..."
    │     │ - Copy to resume/        │ - Save CL MD            │ - "Generating
    │     │                          │ - Generate PDF          │    cover letter..."
    │     │                          │ - Copy to resume/       │ - "Generating
    │     │                          │                         │    cover letter PDF..."
    │     │                          │                         │ - "Cover letter
    │     ↓                          ↓                         │    complete!"
    │  resume_pdf_queue          cl_result_queue              │
    │  {paths, success}          {paths, success}             │
    │     │                          │                         │
    │     └──────────────────────────┴─────────────────────────┘
    │                                │
    ├─ 4. Wait for both threads (join)
    │
    ├─ 5. Check for errors
    │
    ├─ 6. Combine paths from both threads
    │
    └─ 7. Save to database & redirect
```

## Detailed Thread Execution

### Resume PDF Thread

```python
Thread: ResumePDF-{job_id}
Status: Daemon thread

Process:
┌──────────────────────────────────────┐
│ 1. Create Flask app context         │
│    (for database access)             │
├──────────────────────────────────────┤
│ 2. Call save_resume_document()      │
│    - Write resume.md                 │
│    - Convert MD to PDF via md-to-pdf │
│    - Copy to Jass/resume/            │
├──────────────────────────────────────┤
│ 3. Put results in queue              │
│    {                                 │
│      'success': True,                │
│      'paths': {                      │
│        'resume_md': '...',           │
│        'resume_pdf': '...'           │
│      }                               │
│    }                                 │
└──────────────────────────────────────┘

Error Handling:
- Try/catch around entire process
- On error: Put {'success': False, 'error': msg} in queue
```

### Cover Letter Thread

```python
Thread: CoverLetter-{job_id}
Status: Daemon thread

Process:
┌──────────────────────────────────────┐
│ 1. Create Flask app context         │
│    (for database access)             │
├──────────────────────────────────────┤
│ 2. Send SSE event:                   │
│    "Generating cover letter..."      │
├──────────────────────────────────────┤
│ 3. Get custom AI prompts             │
│    from AppSettings                  │
├──────────────────────────────────────┤
│ 4. Initialize AI provider            │
│    (Claude/OpenAI/Ollama/CLI)        │
├──────────────────────────────────────┤
│ 5. Generate cover letter MD          │
│    Using: tailored_resume + job desc │
├──────────────────────────────────────┤
│ 6. Send SSE event:                   │
│    "Generating cover letter PDF..."  │
├──────────────────────────────────────┤
│ 7. Call save_cover_letter_document() │
│    - Write cover_letter.md           │
│    - Convert MD to PDF via md-to-pdf │
│    - Copy to Jass/resume/            │
├──────────────────────────────────────┤
│ 8. Put results in queue              │
│    {                                 │
│      'success': True,                │
│      'paths': {                      │
│        'cover_letter_md': '...',     │
│        'cover_letter_pdf': '...'     │
│      }                               │
│    }                                 │
├──────────────────────────────────────┤
│ 9. Send SSE event:                   │
│    "Cover letter complete!"          │
└──────────────────────────────────────┘

Error Handling:
- Try/catch around entire process
- On error:
  - Put {'success': False, 'error': msg} in queue
  - Send SSE error event
```

## Timing Comparison

### Before Threading (Sequential)

```
Time ─────────────────────────────────────────────────────►

  AI Init │ Resume MD │ Resume PDF │ Cover Letter MD │ Cover Letter PDF │ DB Save
    1s    │    10s    │     5s     │       8s        │        5s        │   1s

Total: 30 seconds
```

### After Threading (Parallel)

```
Time ─────────────────────────────────────────────────────►

  AI Init │ Resume MD │ ┌─ Resume PDF (5s) ─┐ │ DB Save
    1s    │    10s    │ │                    │ │   1s
                       │ └─ Cover Letter MD + PDF (13s) ─┘
                       │
                       └─ (Parallel execution)

Total: ~25 seconds (5s saved by parallelization)

Note: Actual savings depends on relative durations of PDF vs. cover letter generation
```

## Queue Communication Pattern

```
Main Thread                Resume PDF Thread          Cover Letter Thread
     │                            │                           │
     ├─ create resume_pdf_queue   │                           │
     ├─ create cl_result_queue    │                           │
     ├─ create cl_event_queue     │                           │
     │                            │                           │
     ├─ start() ──────────────────►                           │
     ├─ start() ────────────────────────────────────────────► │
     │                            │                           │
     │                            ├─ do work                  ├─ send events ──┐
     │                            │                           │                │
     │                            ├─ put(result)              ├─ do work       │
     │  ◄─── poll cl_event_queue ─┘                          │                │
     │  ◄────────────────────────────────────────────────────┘                │
     │                                                        ├─ put(result)   │
     │                                                        │                │
     ├─ join(timeout=5) ──────────►                          │                │
     ├─ join(timeout=5) ───────────────────────────────────► │                │
     │                            │                           │                │
     ├─ get(resume_pdf_queue)     │                           │                │
     ├─ get(cl_result_queue)      │                           │                │
     │                            │                           │                │
     ├─ combine results            │                           │                │
     ├─ save to database           │                           │                │
     └─ redirect                   │                           │                │
                                  X (thread exits)            X (thread exits)
```

## Error Scenarios

### Scenario 1: Resume PDF Fails, Cover Letter Succeeds

```
Main Thread:
  1. Resume markdown generated ✓
  2. Both threads started ✓
  3. Resume PDF thread returns: {'success': False, 'error': 'PDF conversion failed'}
  4. Cover letter thread returns: {'success': True, 'paths': {...}}
  5. Main thread detects resume PDF error
  6. Raises exception: "Resume PDF generation failed: PDF conversion failed"
  7. SSE error sent to client
  8. No database update
```

### Scenario 2: Cover Letter Fails, Resume PDF Succeeds

```
Main Thread:
  1. Resume markdown generated ✓
  2. Both threads started ✓
  3. Resume PDF thread returns: {'success': True, 'paths': {...}}
  4. Cover letter thread returns: {'success': False, 'error': 'AI generation failed'}
  5. Main thread detects cover letter error
  6. Raises exception: "Cover letter generation failed: AI generation failed"
  7. SSE error sent to client
  8. No database update
```

### Scenario 3: Thread Timeout

```
Main Thread:
  1. Resume markdown generated ✓
  2. Both threads started ✓
  3. join(timeout=5) expires for one thread
  4. get(timeout=1) raises queue.Empty exception
  5. Exception raised: "Cover letter generation thread did not return a result"
  6. SSE error sent to client
  7. No database update

Note: Daemon threads will be killed when main thread exits
```

## Thread Safety Measures

1. **Flask App Context:** Each thread creates its own via `with app.app_context()`
2. **Queue Communication:** Python's queue.Queue is inherently thread-safe
3. **File Paths:** Unique per job (no conflicts between concurrent requests)
4. **Database Write:** Only main thread writes to DB (after joining threads)
5. **Daemon Threads:** Prevent hanging if main thread exits unexpectedly

## Resource Management

```
Thread Lifecycle:
┌────────────────────────────────────────────────────────┐
│ 1. Thread created (not started)                       │
│    Memory: ~2KB (thread object + stack reservation)   │
├────────────────────────────────────────────────────────┤
│ 2. Thread.start() called                              │
│    OS allocates thread stack (~1MB)                   │
│    Thread enters running state                        │
├────────────────────────────────────────────────────────┤
│ 3. Thread executes work                               │
│    Peak memory: Stack + AI model + PDF buffer         │
│    Estimate: 1MB + 50MB + 5MB = ~56MB per thread      │
├────────────────────────────────────────────────────────┤
│ 4. Thread puts result in queue                        │
│    Queue holds reference to result dict               │
├────────────────────────────────────────────────────────┤
│ 5. Thread.join() completes                            │
│    Thread enters dead state                           │
├────────────────────────────────────────────────────────┤
│ 6. Main thread retrieves result from queue            │
│    Queue reference consumed                           │
├────────────────────────────────────────────────────────┤
│ 7. Thread object garbage collected                    │
│    All memory released                                │
└────────────────────────────────────────────────────────┘

Peak Memory (2 threads + main):
- Main thread: ~50MB (baseline)
- Resume PDF thread: ~56MB
- Cover letter thread: ~56MB
- Total: ~162MB (vs ~100MB sequential)
```
