# app

Deploys one git-SHA release of Niyam to Kubernetes and records it in the `niyam-release` ConfigMap. The record is merged rather than replaced so `last_good_tag` survives every deploy. This role needs no sudo, so Jenkins can run it.
