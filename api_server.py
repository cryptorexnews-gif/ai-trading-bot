# Debug: Print detected API key status
    from api.config import API_AUTH_KEY
    api_key_status = "SET ✓" if API_AUTH_KEY else "EMPTY ✗"
    logger.info(f"DASHBOARD_API_KEY status: {api_key_status} (length={len(API_AUTH_KEY) if API_AUTH_KEY else 0})")

    # Security checks (now key is always set)
    if host == "0.0.0.0":
        logger.warning(
            "API server binding to 0.0.0.0 — ensure a reverse proxy with TLS is in front "
            "for production deployments."
        )

    # Never use Flask debug mode in live trading
    if execution_mode == "live" and debug:
        logger.warning("Forcing debug=False because EXECUTION_MODE=live")
        debug = False

    logger.info(
        f"🚀 Starting API server on http://{host}:{port} "
        f"(mode={execution_mode}, debug={debug}, CORS: {CORS_ORIGINS})"
    )
    print(f"\n✅ API Server ready: http://{host}:{port}")
    print(f"   Localhost access: ALLOWED (no API key required)")
    print(f"   Remote access: API key required")
    print(f"   Test: curl http://{host}:{port}/api/health")
    print()