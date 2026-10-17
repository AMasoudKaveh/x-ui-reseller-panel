import unittest
from unittest.mock import patch

from fastapi import HTTPException

import backend.api_v1 as api
from backend.admin_representatives import RepresentativeCreateBody


class ResellerRepresentativeApiTests(unittest.TestCase):
    def principal(self, scopes):
        return api.ApiPrincipal(
            representative_id=7,
            representative_username="root-reseller",
            api_key_id=3,
            api_key_name="automation",
            scopes=frozenset(scopes),
        )

    def test_representative_scopes_are_available_for_api_keys(self):
        for scope in (
            "representatives:read",
            "representatives:create",
            "representatives:update",
            "representatives:reset",
            "representatives:delete",
        ):
            self.assertIn(scope, api.FULL_SCOPES)

    def test_create_endpoint_uses_the_same_panel_create_handler(self):
        body = RepresentativeCreateBody(
            username="child-one",
            password="StrongPassword123!",
            quota_bytes=50 * 1024**3,
            status="Active",
            inbound_ids=[1, 2],
        )
        principal = self.principal({"representatives:create"})

        def call_panel_route(_principal, action, callback, **_kwargs):
            self.assertEqual(action, "representatives.create")
            return callback("temporary-api-session")

        with patch.object(api, "call_panel_route", call_panel_route), \
             patch.object(api, "create_sub_representative") as create:
            create.return_value = {"ok": True, "representative": {"id": 9}}
            result = api.api_create_representative(body, principal)

        self.assertTrue(result["ok"])
        create.assert_called_once_with(body=body, xui_session="temporary-api-session")

    def test_scope_dependency_rejects_key_without_create_permission(self):
        dependency = api.require_scope("representatives:create")
        with self.assertRaises(HTTPException) as raised:
            dependency(self.principal({"representatives:read"}))
        self.assertEqual(raised.exception.status_code, 403)

    def test_representative_routes_are_in_public_openapi_router(self):
        routes = {(method, route.path) for route in api.router.routes for method in route.methods}
        self.assertIn(("POST", "/api/v1/representatives"), routes)
        self.assertIn(("DELETE", "/api/v1/representatives/{representative_id}"), routes)
        self.assertIn(("GET", "/api/v1/representatives/{representative_id}/deletion-preview"), routes)


if __name__ == "__main__":
    unittest.main()
