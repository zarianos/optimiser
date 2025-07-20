# Energy Optimizer Helm Chart

This Helm chart deploys the Kubernetes Energy Optimization System.

## Prerequisites

- Kubernetes 1.20+
- Helm 3.0+
- Prometheus with Kepler metrics

## Installation

```bash
helm install energy-optimizer . -n energy-optimization --create-namespace
```

## Configuration

See values.yaml for configuration options.

## Monitoring

The application exposes Prometheus metrics on port 8080.
