# Architecture diagram

The final diagram is [architecture.png](../architecture.png), with editable source in
[architecture.excalidraw](../architecture.excalidraw). It shows the client-to-NGINX request
path on loopback port 8090, all three Flask replicas, container ports, frontend and internal
backend networks, PostgreSQL and Redis storage, backup output, and health-gated startup
order.

`app-01`, `app-02`, and `app-03` share both application networks. NGINX reaches them only
through the frontend network, while PostgreSQL and Redis remain isolated on the internal
backend network with no published host ports.

Remaining single points of failure and production improvements are explained in
[decisions.md](../decisions.md) and [security_review.md](../security_review.md).
