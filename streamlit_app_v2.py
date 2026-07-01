"""Backward-compatible entry point for older Streamlit launch settings.

The final app entry point is ``streamlit_app.py``. This wrapper keeps older
commands such as ``streamlit run streamlit_app_v2.py`` working.
"""

from streamlit_app import *  # noqa: F401,F403
