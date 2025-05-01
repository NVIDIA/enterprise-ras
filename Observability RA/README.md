**Observability Guide for Enterprise Reference Architectures**

The Observability Guide for Enterprise Reference Architectures (RAs) offers a
standardized and production-ready reference for implementing observability in
enterprise AI or HPC environments. This involves setting up data pipelines and providing
guidance on setting up custom dashboards using tools like NVIDIA Data Center GPU
Manager (DCGM), NIM Operator, Prometheus Node Exporter and other telemetry
sources. These dashboards will ensure improved cluster health visibility as it
experiences AI workloads and accelerated troubleshooting.

This guide builds upon the foundation provided by NVIDIA’s Software Reference
Stack and Automation for Enterprise RAs (available on NVOnline - 1130533) which offers a
modular yet fully integrated software stack for deploying and managing AI workloads
at scale.

To import these Dashboards into Grafana:

 - Download the dashboard JSON file from this repository to your computer

 - Open your Grafana instance in your web browser

 - In the left sidebar, go to Dashboards > New > Import

 - Upload the JSON file you downloaded

 - Select the appropriate data source if prompted, then click Import to finish
