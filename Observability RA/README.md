# Observability Guide for Enterprise Reference Architectures

The Observability Guide for Enterprise Reference Architectures (RAs) offers a standardized and production-ready reference for implementing observability in enterprise AI or HPC environments. This involves setting up data pipelines and providing guidance on setting up custom dashboards using tools like NVIDIA Data Center GPU Manager (DCGM), NIM Operator, Prometheus Node Exporter and other telemetry sources. These dashboards will ensure improved cluster health visibility as it experiences AI workloads and accelerated troubleshooting.As the name suggests this guide is a reference, and end customers are free to use whatever data center provisioning software and/or observability tool to extract and derive insight from metrics

This guide builds upon the foundation provided by NVIDIA's Software Reference Stack and Automation for Enterprise RAs (available on NVOnline - 1130533) which offers a modular yet fully integrated software stack for deploying and managing AI workloads at scale.

### To import the Dashboards into Grafana:

- Download the dashboard JSON file from this repository to your computer
- Open your Grafana instance in your web browser
- In the left sidebar, go to Dashboards > New > Import
- Upload the JSON file you downloaded
- Select the appropriate data source if prompted, then click Import to finish

### To import the Alerts into Grafana:

Before importing alerts, ensure you have completed the prerequisite steps outlined in the Observability Guide Enterprise RA: create a folder on the Dashboards page for organizing alerts, set up a contact point for notifications, and configure an SMTP server for email delivery.

- Download the alert JSON files and the `graf_upload.py` script from this repository
- Open the `config.yaml` file and configure the following parameters:
  - `api_token`: Your Grafana API token
  - `grafana_url`: Your Grafana instance URL
  - `json_files`: Specify the paths to your alert JSON files
- Run the upload script: `python graf_upload.py`
- Verify the alerts are created by navigating to Alerting in your Grafana instance


