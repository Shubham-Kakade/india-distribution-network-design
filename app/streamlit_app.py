"""What-if agent front end (spec §10): chat on the left, the current network on the right.

Run from the project root: streamlit run app/streamlit_app.py
Live mode uses the visitor's own key, typed into the sidebar and held only in this browser
session; locally it can also come from LLM_* variables or a git-ignored .env. With PUBLIC_DEMO=1
the environment is ignored, so a public deployment never uses the owner's key (D-045). Without a
key the app answers from the offline library. The key itself is never shown, logged or stored.
"""

import sys
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # `streamlit run` from the root

from src import viz
from src.agent import Agent, OfflineAgent
from src.agent_offline import LIBRARY_PATH
from src.agent_tools import ToolBox
from src.config import load_params
from src.data_prep import load_network_data
from src.llm_settings import (
    KEY_NOTICE,
    active_config,
    is_public_demo,
    provider_presets,
    user_config,
)
from src.model import COMPONENTS

DISCLAIMER = (
    "Independent portfolio project, not affiliated with Cushman & Wakefield; hypothetical client."
)
MAP_HEIGHT_PX = 470


@st.cache_resource
def load_toolbox() -> ToolBox:
    """Params, network data and every recorded or library scenario, loaded once per server."""
    toolbox = ToolBox(load_params(), load_network_data())
    library = OfflineAgent.from_file().library
    toolbox.records.update(library["records"])  # agent-made networks the library answers with
    return toolbox


def new_agent(toolbox: ToolBox, public: bool) -> Agent:
    """An agent on the visitor's key, else (outside public mode) the .env, else offline."""
    config = active_config(st.session_state.get("user_config"), public)
    return Agent(config, toolbox if config.live else None, OfflineAgent.from_file())


# --- Live mode panel: the key lives only in st.session_state (D-045) ----------------------


def fill_preset(public: bool) -> None:
    base_url, model = provider_presets(public)[st.session_state.provider]
    st.session_state.base_url, st.session_state.model = base_url, model


def use_key(toolbox: ToolBox, public: bool) -> None:
    try:
        st.session_state.user_config = user_config(
            st.session_state.base_url, st.session_state.key_input, st.session_state.model, public
        )
        st.session_state.key_error = None
    except ValueError as err:  # messages never echo the key
        st.session_state.key_error = str(err)
        return
    finally:
        st.session_state.key_input = ""  # the key is kept once, in user_config, not in the field
    st.session_state.agent = new_agent(toolbox, public)


def forget_key(toolbox: ToolBox, public: bool) -> None:
    st.session_state.user_config = None
    st.session_state.key_input = ""
    st.session_state.key_error = None
    st.session_state.agent = new_agent(toolbox, public)


def live_mode_panel(toolbox: ToolBox, public: bool) -> None:
    presets = provider_presets(public)
    if "provider" not in st.session_state:
        st.session_state.provider = next(iter(presets))
        fill_preset(public)
    st.subheader("Live mode")
    st.caption(KEY_NOTICE)
    st.selectbox("Provider", list(presets), key="provider", on_change=fill_preset, args=(public,))
    st.text_input("Base URL", key="base_url")
    st.text_input("Model", key="model")
    st.text_input("API key", key="key_input", type="password", autocomplete="off")
    use, forget = st.columns(2)
    use.button("Use this key", on_click=use_key, args=(toolbox, public))
    forget.button("Forget key", on_click=forget_key, args=(toolbox, public))
    if st.session_state.get("key_error"):
        st.error(st.session_state.key_error)


def network_panel(toolbox: ToolBox, scenario_id: str) -> None:
    """Map of the scenario's network and its cost by component against the recommended one."""
    record = toolbox.record(scenario_id)
    params = toolbox.params
    if "cost_cr" not in record:
        st.info(f"{scenario_id}: no feasible network to draw.")
        return
    solution = SimpleNamespace(
        open_dcs=tuple(record["open_dcs"]), assignment=pd.Series(record["assignment"])
    )
    radius_km = params["service"]["next_day_radius_km"]["value"]
    ring_gc_km = radius_km / params["distance"]["circuity_factor"]["value"]
    title = (
        f"{scenario_id}: {len(record['open_dcs'])} DCs, INR {record['cost_cr']['total']:.1f} Cr/yr,"
        f" {record['service']['next_day_share_frac']:.1%} next-day"
    )
    fmap = viz.plot_network_map(
        toolbox.data_for(record["open_dcs"]), solution, radius_km, ring_gc_km, title, DISCLAIMER
    )
    components.html(fmap.get_root().render(), height=MAP_HEIGHT_PX)
    rec = toolbox.recommended_record
    fig = viz.plot_cost_comparison(
        {c: record["cost_cr"][c] for c in COMPONENTS},
        {c: rec["cost_cr"][c] for c in COMPONENTS},
        scenario_id,
        toolbox.recommended_id,
    )
    st.pyplot(fig)
    if "outage_cost_cr" in record["extra"]:
        st.caption(
            "Annual run rate while the site is shut. The outage itself is charged only the extra "
            "freight for its months; rent, fixed cost and stock stay in place (D-029)."
        )


def main() -> None:
    st.set_page_config(page_title="India DC network: what-if agent", layout="wide")
    toolbox = load_toolbox()
    public = is_public_demo()
    if "agent" not in st.session_state:
        st.session_state.agent = new_agent(toolbox, public)
        st.session_state.turns = []
        st.session_state.scenario_id = toolbox.recommended_id
    agent: Agent = st.session_state.agent

    with st.sidebar:
        st.header("Agent")
        config = agent.config
        live = agent.mode == "live"
        st.write(f"**Mode:** {agent.mode}")
        st.write(f"**Provider:** {config.provider if live else 'offline library'}")
        st.write(f"**Model:** {config.model if live else 'none (no network)'}")
        st.write(f"**Key:** {config.source if live else 'none'}")  # the source, never the key
        st.caption(f"Offline library: {LIBRARY_PATH.name}, 20 pre-computed questions.")
        live_mode_panel(toolbox, public)
        st.subheader("Try")
        for entry in agent.offline.library["entries"][:8]:
            st.caption(entry["example"])

    st.title("India distribution network: what-if agent")
    chat, network = st.columns([1, 1])
    question = st.chat_input("Ask a what-if question, e.g. What if Hosur shuts for a month?")
    if question:
        with st.spinner("Running the model..."):
            reply = agent.ask(question)
        st.session_state.turns.append((question, reply))
        for sid in reply.scenario_ids:  # show the first cited scenario that is a network
            try:
                toolbox.record(sid)
            except ValueError:  # a table such as S9_tornado
                continue
            st.session_state.scenario_id = sid
            break

    with chat:
        for asked, reply in st.session_state.turns:
            st.chat_message("user").write(asked)
            with st.chat_message("assistant"):
                if reply.notice:
                    st.warning(reply.notice)
                st.markdown(reply.text)
                tools = ", ".join(name for name, _ in reply.tool_calls) or "none"
                st.caption(f"{reply.mode} · tools: {tools} · grounding: {reply.grounding}")
    with network:
        st.subheader(st.session_state.scenario_id)
        network_panel(toolbox, st.session_state.scenario_id)

    st.divider()
    st.caption(DISCLAIMER)


main()
