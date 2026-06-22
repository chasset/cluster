"""Tests de nestor/portal.py (ADR 0091 / ADR 0017 : logique pure testée sans cluster).

Croisement contrat ↔ état observé : verdicts (MATCH/MISSING/DRIFT/EXTRA), génération
des commandes secret (jamais la valeur), groupage par couche. Aucun I/O cluster.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from nestor.portal import (  # noqa: E402
    DRIFT,
    EXTRA,
    LAYER_ORDER,
    MATCH,
    MISSING,
    Observed,
    build_view,
    secret_command,
)

# Endpoints d'exemple (sous-ensemble du contrat réel, formes variées d'auth).
_EP = [
    {
        "id": "grafana-ui",
        "service": "kube-prometheus-stack-grafana",
        "namespace": "monitoring",
        "port": 80,
        "auth": "secret-admin",
        "layer": "monitoring",
        "ui_hostname": "grafana.cluster.lan",
    },
    {
        "id": "argocd-ui",
        "service": "argocd-server",
        "namespace": "argocd",
        "port": 80,
        "auth": "secret-admin",
        "layer": "gitops",
        "ui_hostname": "argocd.cluster.lan",
    },
    {
        "id": "mlflow-tracking",
        "service": "mlflow",
        "namespace": "mlflow",
        "port": 5000,
        "auth": "none",
        "layer": "dataops",
    },
    {
        "id": "mailpit-ui",
        "service": "mailpit",
        "namespace": "mailpit",
        "port": 8025,
        "auth": "none",
        "layer": "monitoring",
        "profil": "local-path",
    },
    {
        "id": "k8s-dashboard-ui",
        "service": "kubernetes-dashboard",
        "namespace": "kubernetes-dashboard",
        "port": 443,
        "auth": "token",
        "layer": "socle",
        "ui_hostname": "dashboard.cluster.lan",
    },
]


class SecretCommand(unittest.TestCase):
    def test_none_returns_no_command(self):
        self.assertIsNone(secret_command({"id": "mlflow", "auth": "none"}))
        self.assertIsNone(secret_command({"id": "x"}))  # auth absent = none

    def test_secret_admin_known_refs(self):
        cmd = secret_command({"id": "argocd-ui", "namespace": "argocd", "auth": "secret-admin"})
        self.assertIn("kubectl -n argocd get secret argocd-initial-admin-secret", cmd)
        self.assertIn("base64 -d", cmd)

    def test_grafana_admin_password_key(self):
        cmd = secret_command(
            {"id": "grafana-ui", "namespace": "monitoring", "auth": "secret-admin"}
        )
        self.assertIn("admin-password", cmd)

    def test_token_uses_create_token(self):
        cmd = secret_command(
            {"id": "k8s-dashboard-ui", "namespace": "kubernetes-dashboard", "auth": "token"}
        )
        self.assertIn("create token", cmd)

    def test_secret_role_derives_pg_role(self):
        cmd = secret_command(
            {"id": "postgres-rw", "namespace": "postgres", "auth": "secret-role", "role": "dagster"}
        )
        self.assertIn("pg-role-dagster", cmd)

    def test_obc_secret_key(self):
        cmd = secret_command({"id": "s3", "namespace": "rook-ceph", "auth": "secret-obc"})
        self.assertIn("AWS_SECRET_ACCESS_KEY", cmd)

    def test_never_contains_a_value(self):
        # Le portail montre la COMMANDE, jamais une valeur de secret (ADR 0091 §3).
        cmd = secret_command({"id": "gitea-ui", "namespace": "gitea", "auth": "secret-admin"})
        self.assertIn("jsonpath", cmd)  # une commande de lecture, pas un littéral


class Verdicts(unittest.TestCase):
    def test_match_when_present_ready_right_host(self):
        obs = {
            ("monitoring", "kube-prometheus-stack-grafana"): Observed(
                present=True, ready=True, hostname="grafana.cluster.lan"
            )
        }
        v = build_view(_EP, obs)
        grafana = next(e for e in v.all_entries() if e.id == "grafana-ui")
        self.assertEqual(grafana.verdict, MATCH)
        self.assertEqual(grafana.ui_url, "https://grafana.cluster.lan")

    def test_missing_when_absent(self):
        v = build_view(_EP, {})  # rien observé
        argocd = next(e for e in v.all_entries() if e.id == "argocd-ui")
        self.assertEqual(argocd.verdict, MISSING)

    def test_drift_when_present_not_ready(self):
        obs = {("argocd", "argocd-server"): Observed(present=True, ready=False)}
        v = build_view(_EP, obs)
        self.assertEqual(next(e for e in v.all_entries() if e.id == "argocd-ui").verdict, DRIFT)

    def test_drift_when_hostname_differs(self):
        obs = {
            ("monitoring", "kube-prometheus-stack-grafana"): Observed(
                present=True, ready=True, hostname="autre.cluster.lan"
            )
        }
        v = build_view(_EP, obs)
        self.assertEqual(next(e for e in v.all_entries() if e.id == "grafana-ui").verdict, DRIFT)

    def test_banc_only_absent_in_prod_is_match(self):
        # mailpit (profil local-path) absent en prod → MATCH (attendu), pas MISSING.
        v = build_view(_EP, {}, target_is_prod=True)
        self.assertEqual(next(e for e in v.all_entries() if e.id == "mailpit-ui").verdict, MATCH)

    def test_banc_only_absent_on_bench_is_missing(self):
        # sur le banc (target_is_prod=False), un banc-only absent EST manquant.
        v = build_view(_EP, {}, target_is_prod=False)
        self.assertEqual(next(e for e in v.all_entries() if e.id == "mailpit-ui").verdict, MISSING)

    def test_extra_for_observed_outside_contract(self):
        v = build_view(
            _EP,
            {},
            extras=[{"id": "rogue", "service": "rogue", "namespace": "x", "layer": "dataops"}],
        )
        rogue = next(e for e in v.all_entries() if e.id == "rogue")
        self.assertEqual(rogue.verdict, EXTRA)


class Grouping(unittest.TestCase):
    def test_grouped_by_layer_in_canonical_order(self):
        v = build_view(_EP, {})
        # les couches présentes apparaissent dans l'ordre canonique (socle avant dataops).
        present = [layer for layer in v.layers]
        canonical = [layer for layer in LAYER_ORDER if layer in present]
        self.assertEqual(present[: len(canonical)], canonical)

    def test_each_entry_in_its_layer(self):
        v = build_view(_EP, {})
        self.assertIn("argocd-ui", [e.id for e in v.layers["gitops"]])
        self.assertIn("mlflow-tracking", [e.id for e in v.layers["dataops"]])

    def test_no_auth_no_secret_cmd(self):
        v = build_view(_EP, {})
        mlflow = next(e for e in v.all_entries() if e.id == "mlflow-tracking")
        self.assertIsNone(mlflow.secret_cmd)
        argocd = next(e for e in v.all_entries() if e.id == "argocd-ui")
        self.assertIsNotNone(argocd.secret_cmd)


if __name__ == "__main__":
    unittest.main()
