# Fraud Shield

An assistive algorithmic automation tool to identify suspicious transactions (unusual spending, sudden large refunds, rapid fire card charges) for small businesses. 

It builds a baseline of "normal" behavior for each customer and flags transactions that deviate significantly from their typical activity.

## Files in this Repository

`fraud_detector.py` – Core detection logic and CLI interface.
`app.py` – Interactive Streamlit web interface.
`sample_transactions.csv` – Sample dataset containing labeled synthetic fraud.
`requirements.txt` – Python dependencies.

> Keep all files in the same root directory when running the tool.

## Quick Start
python -m streamlit run app.py
### 1. Install Dependencies
python -m pip install -r requirements.txt