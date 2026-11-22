# ingest

Runs a Kubernetes Job named after the release to index the corpus into Qdrant. Unchanged documents are skipped, so running it on every release is safe and also restores the index if Qdrant loses its data. A failed Job fails the release.
