# minikube

Starts the `niyam` profile with ingress published on `127.0.0.1:80`, enables the required addons, waits for ingress, and refreshes the Jenkins kubeconfig because the API port can change after a WSL restart. Only the Jenkins kubeconfig tasks need sudo.
