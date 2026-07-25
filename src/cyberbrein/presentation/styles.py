import streamlit as st

DASHBOARD_CSS = """
<style>
    .stMainBlockContainer {
        max-width: 1180px;
        padding-top: 2rem;
        padding-bottom: 3rem;
    }
    [data-testid="stMetric"] {
        min-height: 116px;
    }
    [data-testid="stMetricValue"] {
        font-weight: 650;
    }
    .cb-eyebrow {
        color: #68736f;
        font-size: 0.78rem;
        font-weight: 700;
        letter-spacing: 0.08em;
        margin-bottom: 0.2rem;
        text-transform: uppercase;
    }
    .cb-context {
        color: #43504c;
        font-size: 0.95rem;
        padding-top: 0.55rem;
    }
    .cb-privacy-note {
        background: #ffffff;
        border: 1px solid #dfe3df;
        border-radius: 0.5rem;
        color: #55615d;
        margin-top: 0.4rem;
        padding: 0.8rem 1rem;
    }
    @media (max-width: 768px) {
        .stMainBlockContainer {
            padding-left: 1rem;
            padding-right: 1rem;
            padding-top: 1.25rem;
        }
        [data-testid="stHorizontalBlock"] {
            flex-wrap: wrap;
        }
        [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
            flex: 1 1 100% !important;
            min-width: 100% !important;
            width: 100% !important;
        }
        [data-testid="stMetric"] {
            min-height: auto;
        }
    }
</style>
"""


def apply_dashboard_styles() -> None:
    st.markdown(DASHBOARD_CSS, unsafe_allow_html=True)
