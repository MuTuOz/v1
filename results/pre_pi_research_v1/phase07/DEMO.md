# Demonstration instructions

From the SeniorProject root:

```bash
/home/seniorfl/seniorproject-fl-venv/bin/python -m streamlit run dashboard/app.py --server.address 127.0.0.1 --server.port 8501 --browser.gatherUsageStats false
```

Open http://127.0.0.1:8501 locally. Start with Overview, select a local client,
then Locally unseen attacks (A, B, C), Confusion matrices and Formal HCM. Show
Repeated seeds, Class imbalance (including failed weighting outcomes), Non-IID,
Limitations and the future physical section. Every value is loaded from saved
results. No model fitting, packet generation or network setup button exists.
For an unavailable optional artifact the dashboard displays "Not yet available."

AppTest exercises all 11 views and the three confusion levels. A localhost HTTP
health check was executed. No real-browser screenshot is claimed; figures in
`figures/` are measured-data academic plots, not fabricated UI screenshots.
