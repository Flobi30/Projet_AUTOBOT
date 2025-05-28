Sure! Below are the requested files for a Python application using Docker, Docker Compose, Kubernetes, and Helm.

### 1. Dockerfile

```dockerfile
# Use the official Python 3.11 slim image
FROM python:3.11-slim

# Set the working directory
WORKDIR /app

# Copy the requirements file
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code
COPY . .

# Command to run the application
CMD ["python", "app.py"]
```

### 2. docker-compose.yml

```yaml
version: '3.8'

services:
  app:
    build: .
    ports:
      - "5000:5000"
    environment:
      - ENV=development
    volumes:
      - .:/app
    command: python app.py
```

### 3. Kubernetes Manifests

#### k8s/deployment.yaml

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: python-app
  labels:
    app: python-app
spec:
  replicas: 3
  selector:
    matchLabels:
      app: python-app
  template:
    metadata:
      labels:
        app: python-app
    spec:
      containers:
      - name: python-app
        image: your-docker-repo/python-app:latest
        ports:
        - containerPort: 5000
        env:
        - name: ENV
          value: "production"
```

#### k8s/service.yaml

```yaml
apiVersion: v1
kind: Service
metadata:
  name: python-app
spec:
  type: ClusterIP
  ports:
    - port: 5000
      targetPort: 5000
  selector:
    app: python-app
```

#### k8s/hpa.yaml

```yaml
apiVersion: autoscaling/v2beta2
kind: HorizontalPodAutoscaler
metadata:
  name: python-app-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: python-app
  minReplicas: 1
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 50
```

### 4. Helm Chart Skeleton

```plaintext
charts/
└── python-app/
    ├── Chart.yaml
    ├── values.yaml
    ├── templates/
    │   ├── deployment.yaml
    │   ├── service.yaml
    │   └── hpa.yaml
```

#### charts/python-app/Chart.yaml

```yaml
apiVersion: v2
name: python-app
description: A Helm chart for Kubernetes deployment of a Python application
version: 0.1.0
appVersion: "3.11"
```

#### charts/python-app/values.yaml

```yaml
replicaCount: 3

image:
  repository: your-docker-repo/python-app
  pullPolicy: IfNotPresent
  tag: latest

service:
  type: ClusterIP
  port: 5000

resources: {}
```

#### charts/python-app/templates/deployment.yaml

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ .Release.Name }}-app
  labels:
    app: {{ .Release.Name }}-app
spec:
  replicas: {{ .Values.replicaCount }}
  selector:
    matchLabels:
      app: {{ .Release.Name }}-app
  template:
    metadata:
      labels:
        app: {{ .Release.Name }}-app
    spec:
      containers:
      - name: {{ .Release.Name }}-app
        image: "{{ .Values.image.repository }}:{{ .Values.image.tag }}"
        ports:
        - containerPort: {{ .Values.service.port }}
        env:
        - name: ENV
          value: "production"
```

#### charts/python-app/templates/service.yaml

```yaml
apiVersion: v1
kind: Service
metadata:
  name: {{ .Release.Name }}-app
spec:
  type: {{ .Values.service.type }}
  ports:
    - port: {{ .Values.service.port }}
      targetPort: {{ .Values.service.port }}
  selector:
    app: {{ .Release.Name }}-app
```

#### charts/python-app/templates/hpa.yaml

```yaml
apiVersion: autoscaling/v2beta2
kind: HorizontalPodAutoscaler
metadata:
  name: {{ .Release.Name }}-app-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: {{ .Release.Name }}-app
  minReplicas: 1
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 50
```

### Notes
- Replace `your-docker-repo/python-app` with your actual Docker repository.
- Ensure you have a `requirements.txt` file in your project directory for the Python dependencies.
- Adjust the application entry point in the Dockerfile and the command in the Docker Compose file as necessary.

