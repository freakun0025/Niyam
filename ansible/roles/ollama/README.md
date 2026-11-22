# ollama

Uses the Ollama already running on the host, pulls the configured model if it is missing, and publishes it inside the cluster through a selector-less Service and EndpointSlice. This role needs no sudo and does not change the Ollama service.
