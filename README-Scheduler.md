# Marketing Agents Scheduler

Automated scheduler for running all Marketing Agents components on regular intervals.

## Components & Schedules

| Component | Frequency | Time | Description |
|-----------|-----------|------|-------------|
| RSS Feeder | Daily | 6:00 AM | Collects RSS articles from configured sources |
| Weekly Digest | Weekly | Sunday 7:00 AM | Generates top articles summary for past week |
| Serpi Feeder | Weekly | Sunday 8:00 AM | Collects Google Trends data via SerpAPI |
| Tavily Feeder | Weekly | Sunday 9:00 AM | Collects research data via Tavily API |
| Reddit Watcher | Weekly | Sunday 10:00 AM | Scrapes Reddit trends and discussions |
| Vector DB Update | Weekly | Sunday 11:00 AM | Updates vector database with new content |

## Setup

1. Install scheduler dependencies:
   ```bash
   pip install -r requirements-scheduler.txt
   ```

2. Ensure all component dependencies are installed in their respective directories.

## Usage

### Test Run (run all tasks once)
```bash
python scheduler.py --run-once
```

### Start Automated Scheduler
```bash
python scheduler.py --schedule
```

The scheduler will run continuously, checking for scheduled tasks every minute. Use Ctrl+C to stop.

## Output Timestamping

All components automatically timestamp their outputs:
- RSS data: `data/raw/rss_YYYY-MM-DD.json`
- Weekly digests: `data/weekly/YYYY-WW.json`
- Google Trends: `outputs/YYYY-MM-DD_HH-MM.json`
- Research data: `results/YYYY-MM-DD_HH-MM.json`
- Reddit data: `output/reddit_raw.json` and `output/reddit_trends.xlsx`

## Windows Task Scheduler

For production use, create a Windows Task Scheduler task to run the scheduler:

1. Open Task Scheduler
2. Create new task
3. Set trigger: Daily at desired start time
4. Set action: Start program
   - Program: `python.exe`
   - Arguments: `scheduler.py --schedule`
   - Start in: `C:\Users\acer\PycharmProjects\Marketing_agents`
5. Configure for highest privileges if needed

## Monitoring

The scheduler logs all activity to console with emojis:
- ✅ Task completed successfully
- ❌ Task failed
- ⏰ Task timed out
- 🔄 Task starting

Check the console output for detailed status and error messages.</content>
<parameter name="filePath">c:\Users\acer\PycharmProjects\Marketing_agents\README-Scheduler.md