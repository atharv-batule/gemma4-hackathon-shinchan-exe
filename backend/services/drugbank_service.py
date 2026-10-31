"""DrugBank adapter status. The interaction API is not called without a
documented authorized endpoint and credentials for the installation.
"""
import os


def interaction_lookup(*args, **kwargs) -> dict:
    credential_configured = bool(os.getenv("DRUGBANK_API_KEY", "").strip())
    endpoint_configured = bool(os.getenv("DRUGBANK_API_BASE", "").strip())
    if credential_configured and endpoint_configured:
        reason = "Credentials and base URL are configured, but no endpoint/schema adapter has been verified for this DrugBank account. No request was sent."
    elif credential_configured:
        reason = "A DrugBank key is configured, but DRUGBANK_API_BASE and an account-specific endpoint/schema are not verified. No request was sent."
    else:
        reason = "DrugBank interaction data requires authorized access and credentials; none are configured."
    return {"status":"unavailable", "source":"DrugBank", "records":[],
            "credential_configured":credential_configured,
            "endpoint_configured":endpoint_configured, "error":reason}
