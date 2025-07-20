.PHONY: build push run test clean helm-package helm-install

# Variables
IMAGE_NAME := energy-optimizer
IMAGE_TAG := latest
REGISTRY := your-registry.com
NAMESPACE := energy-optimization

# Build Docker image
build:
	docker build -t $(IMAGE_NAME):$(IMAGE_TAG) .

# Tag and push to registry
push: build
	docker tag $(IMAGE_NAME):$(IMAGE_TAG) $(REGISTRY)/$(IMAGE_NAME):$(IMAGE_TAG)
	docker push $(REGISTRY)/$(IMAGE_NAME):$(IMAGE_TAG)

# Run locally with docker compose
run:
	docker compose up -d

# Stop local deployment
stop:
	docker compose down

# Run tests
test:
	docker run --rm -v $(PWD):/app $(IMAGE_NAME):$(IMAGE_TAG) pytest

# Clean up
clean:
	docker compose down -v
	docker rmi $(IMAGE_NAME):$(IMAGE_TAG) || true
	rm -rf __pycache__ .pytest_cache

# Helm operations
helm-package:
	cd helm && helm package energy-optimizer/

helm-install:
	helm install energy-optimizer energy-optimizer/ \
		--namespace $(NAMESPACE) \
		--create-namespace \
		--set image.repository=$(REGISTRY)/$(IMAGE_NAME) \
		--set image.tag=$(IMAGE_TAG)

helm-upgrade:
	helm upgrade energy-optimizer energy-optimizer/ \
		--namespace $(NAMESPACE) \
		--set image.repository=$(REGISTRY)/$(IMAGE_NAME) \
		--set image.tag=$(IMAGE_TAG)

helm-uninstall:
	helm uninstall energy-optimizer --namespace $(NAMESPACE)

# Development helpers
logs:
	docker compose logs -f energy-optimizer

shell:
	docker run --rm -it -v $(PWD):/app $(IMAGE_NAME):$(IMAGE_TAG) /bin/bash

# Build and run everything
all: build run

# Check if everything is working
healthcheck:
	curl -f http://localhost:8080/metrics || echo "Health check failed"
