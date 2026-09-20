"""Repo Auditor - Windows-Native Streamlit App.

Packer with AST one-hop import resolution, char cap, and 3-pass Agnes AI Auditor.
"""

import json
from pathlib import Path

import streamlit as st

from src.audit import DEFAULT_AUDIT_CACHE, run_three_pass_audit
from src.config import get_config
from src.pack import DEFAULT_PACK_CACHE, PackResult, pack_repository
from src.providers import get_available_providers
from src.safety import validate_repo_path

st.set_page_config(
    page_title="Repo Auditor",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Initialize Session State
st.session_state.setdefault("selected_repo_path", "")
st.session_state.setdefault("base_ref", "")
st.session_state.setdefault("head_ref", "")
st.session_state.setdefault("file_cap", 40)
st.session_state.setdefault("char_cap", 80_000)
st.session_state.setdefault("pack_result", None)
st.session_state.setdefault("audit_result", None)
st.session_state.setdefault("active_nav", "Health")


def set_page(page_name: str):
    """Set the Streamlit page and rerun to render it.

    Args:
        page_name: One of the page names listed in ``PAGES``.
    """
    st.session_state.active_nav = page_name
    st.rerun()


# --- Sidebar Navigation & Model Provider ---
st.sidebar.title("🛡️ Repo Auditor")
st.sidebar.caption("Surgical Codebase Auditing & Packing")

PAGES = ["Health", "Select", "Pack", "Audit", "Findings"]
page_options = PAGES
nav_choice = st.sidebar.radio(
    "Navigation",
    options=page_options,
    index=page_options.index(st.session_state.active_nav)
    if st.session_state.active_nav in page_options
    else 0,
)

if nav_choice != st.session_state.active_nav:
    st.session_state.active_nav = nav_choice

st.sidebar.divider()
st.sidebar.subheader("Pack settings")
st.sidebar.number_input(
    "budget_chars",
    min_value=10_000,
    max_value=500_000,
    step=10_000,
    key="char_cap",
)
st.sidebar.number_input(
    "max_files",
    min_value=1,
    max_value=200,
    step=1,
    key="file_cap",
)

st.sidebar.divider()
st.sidebar.subheader("Model")

available_providers = get_available_providers()
selected_provider_name = "Agnes AI"
current_provider = available_providers[selected_provider_name]
selected_model = current_provider.default_model
st.sidebar.text(selected_model)
if current_provider.has_api_key:
    st.sidebar.success(f"{current_provider.api_key_env_var} is available")
else:
    st.sidebar.warning(f"{current_provider.api_key_env_var} is missing")

if st.session_state.pack_result:
    st.sidebar.divider()
    st.sidebar.subheader("Active Workspace")
    res: PackResult = st.session_state.pack_result
    st.sidebar.text(f"Target: {res.repo_path.name}")
    st.sidebar.text(
        f"Mode: {'Git (' + res.ref_or_glob + ')' if res.is_git else 'Folder scan (' + res.ref_or_glob + ')'}"
    )
    st.sidebar.text(f"Files: {res.total_files} ({res.total_chars:,} chars)")


# --- Page 1: Health ---
if st.session_state.active_nav == "Health":
    config = get_config()
    st.title("Health")
    st.metric("AGNESAI_API_KEY set", "Yes" if config.agnes_api_key_set else "No")
    st.caption("Presence check only. Repo Auditor never displays the key.")
    st.code(f"Model: {config.model}\nBase URL: {config.base_url}", language="text")
    if st.button("Continue to Select", type="primary"):
        set_page("Select")


# --- Page 2: Select ---
elif st.session_state.active_nav == "Select":
    st.title("📁 Select repository or folder")
    st.markdown(
        "Enter local path to a Git repository or project folder. Refuses to scan without an entered path or if set to a drive root (`D:\\`, `C:\\`)."
    )

    if st.button("Load fixture"):
        fixture = Path(__file__).resolve().parent / "data" / "fixtures" / "mini_pkg"
        st.session_state.selected_repo_path = str(fixture)
        st.session_state.pack_result = None
        st.session_state.audit_result = None

    repo_input = st.text_input(
        "Local repository or folder path",
        value=st.session_state.selected_repo_path,
        placeholder="e.g. D:\\AI\\Github\\repo-auditor",
        help="Target folder. If .git is present, git diff mode is used; otherwise glob mode is used.",
    )

    typed_valid, _, typed_target = validate_repo_path(repo_input)
    if typed_valid and typed_target is not None and (typed_target / ".git").exists():
        st.caption("Git repository detected. Optional refs use a read-only `git diff --name-only`.")
        base_col, head_col = st.columns(2)
        with base_col:
            st.session_state.base_ref = st.text_input(
                "Base ref", value=st.session_state.base_ref, placeholder="main"
            )
        with head_col:
            st.session_state.head_ref = st.text_input(
                "Head ref", value=st.session_state.head_ref, placeholder="HEAD"
            )

    if st.button("Inspect target", type="primary"):
        valid, message, target = validate_repo_path(repo_input)
        if not valid or target is None:
            st.error(f"Refusing to scan: {message}")
        else:
            st.session_state.selected_repo_path = str(target)
            st.session_state.pack_result = None
            st.session_state.audit_result = None
            st.success(message)

    if st.session_state.selected_repo_path:
        p = Path(st.session_state.selected_repo_path)
        if p.exists() and p.is_dir():
            st.info(f"Target selected: **{p}** ({'Git' if (p / '.git').exists() else 'Non-Git'})")
            if st.button("Proceed to Pack ➡️"):
                set_page("Pack")


# --- Page 3: Pack ---
elif st.session_state.active_nav == "Pack":
    st.title("📦 Repository Packer")

    if not st.session_state.selected_repo_path:
        st.warning("No target selected. Return to 'Select' and type a path first.")
        if st.button("⬅️ Go to Select"):
            set_page("Select")
    else:
        st.markdown(f"Target: `{st.session_state.selected_repo_path}`")
        col_act1, col_act2 = st.columns([1, 4])
        with col_act1:
            pack_button = st.button("Gather & Pack Files", type="primary")

        if pack_button:
            base_ref = st.session_state.base_ref.strip()
            head_ref = st.session_state.head_ref.strip()
            if bool(base_ref) != bool(head_ref):
                st.error("Enter both Base ref and Head ref, or leave both empty.")
            else:
                git_refs = f"{base_ref}..{head_ref}" if base_ref and head_ref else None
                with st.spinner("Packing repository files & resolving AST dependencies..."):
                    ok, msg, res = pack_repository(
                        root_path=st.session_state.selected_repo_path,
                        git_refs=git_refs,
                        budget_chars=st.session_state.char_cap,
                        max_files=st.session_state.file_cap,
                        auto_cache=True,
                    )
                if ok and res:
                    st.session_state.pack_result = res
                    if res.git_error:
                        st.warning(res.git_error)
                    st.success(f"{msg} Saved to `data/cache/last_pack.json`.")
                else:
                    st.error(f"Packaging failed: {msg}")

        if st.session_state.pack_result:
            res: PackResult = st.session_state.pack_result

            # Metrics
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Packed files", res.total_files)
            m2.metric("Pack size", f"{res.total_chars:,} chars")
            m3.metric("Budget", f"{res.total_chars:,} / {res.char_cap:,}")
            m4.metric("Est. Tokens", f"~{res.token_estimate:,}")

            if res.one_hop_links:
                st.subheader("🔗 AST One-Hop Local Import Graph")
                for src_file, deps in res.one_hop_links.items():
                    st.markdown(f"- `{src_file}` imports: {', '.join(f'`{d}`' for d in deps)}")

            # Manifest Table
            st.subheader("📋 Pack Manifest")
            manifest_data = [
                {
                    "Path": item.path,
                    "Size (bytes)": item.bytes,
                    "Included": item.included,
                    "Reason": item.reason,
                }
                for item in res.manifest
            ]
            st.dataframe(manifest_data, width="stretch", height=280)

            # Download Pack Manifest JSON
            cache_pack_path = DEFAULT_PACK_CACHE
            if cache_pack_path.exists():
                st.download_button(
                    "Download Pack Manifest (JSON)",
                    data=cache_pack_path.read_text(encoding="utf-8"),
                    file_name="last_pack.json",
                    mime="application/json",
                )

            # File Preview
            if res.files:
                st.subheader("🔍 File Preview")
                chosen_file = st.selectbox(
                    "Select file to view", options=[f.rel_path for f in res.files]
                )
                matched = next((f for f in res.files if f.rel_path == chosen_file), None)
                if matched:
                    tags = []
                    if matched.is_diff_match:
                        tags.append("Changed File")
                    if matched.is_ast_import:
                        tags.append(f"AST Import (from {matched.imported_by})")
                    st.caption(
                        f"{matched.lines} lines | {matched.size_bytes:,} bytes | {', '.join(tags)}"
                    )
                    st.code(matched.content, language=matched.extension.replace(".", "") or "text")

            st.divider()
            if st.button("Proceed to Audit ➡️"):
                set_page("Audit")


# --- Page 4: Audit ---
elif st.session_state.active_nav == "Audit":
    st.title("🔍 Multi-Pass AI Auditor")

    if not st.session_state.pack_result:
        st.warning("No files packed. Please pack files on the 'Pack' page before auditing.")
        if st.button("⬅️ Go to Pack"):
            set_page("Pack")
    else:
        res = st.session_state.pack_result
        st.markdown(
            f"Auditing **{res.total_files} files** ({res.total_chars:,} chars) using **{selected_model}**."
        )

        st.markdown(
            """
            **Three Distinct Passes:**
            1. **api_drift** — Broken imports, renamed callees, and missing symbols.
            2. **secrets_patterns** — Hardcoded key-like assignments and `shell=True` locations only.
            3. **tests** — Missing tests for changed or public functions.
            """
        )

        if st.button("Run 3-Pass AI Audit", type="primary"):
            progress_bar = st.progress(0)
            status_text = st.empty()

            def update_progress(label: str, percent: int):
                status_text.text(label)
                progress_bar.progress(percent)

            try:
                with st.spinner("Executing separate audit passes with Agnes AI..."):
                    audit_res = run_three_pass_audit(
                        pack_result=res,
                        provider_name=selected_provider_name,
                        model_name=selected_model,
                        progress_callback=update_progress,
                    )
                    st.session_state.audit_result = audit_res
                    status_text.text("Audit complete!")
                    progress_bar.progress(100)
                    st.success(
                        f"Completed! Generated {len(audit_res['findings'])} structured findings. Saved to `data/cache/last_audit.json`."
                    )
            except Exception as exc:
                st.error(f"Audit failed: {exc}")

        if st.session_state.audit_result:
            audit = st.session_state.audit_result
            c1, c2, c3 = st.columns(3)
            c1.metric("API Drift Findings", audit["pass_summaries"].get("api_drift", 0))
            c2.metric("Security Findings", audit["pass_summaries"].get("secrets_patterns", 0))
            c3.metric("Missing Test Findings", audit["pass_summaries"].get("tests", 0))

            st.dataframe(audit["findings"], width="stretch")
            st.download_button(
                "Download Findings (JSON)",
                data=json.dumps(audit, indent=2),
                file_name="last_audit.json",
                mime="application/json",
                key="audit_download",
            )

            st.divider()
            if st.button("View Findings ➡️"):
                set_page("Findings")


# --- Page 5: Findings ---
elif st.session_state.active_nav == "Findings":
    st.title("📋 Audit Findings")

    # Load from session or cached file
    findings_data = st.session_state.audit_result
    cache_path = DEFAULT_AUDIT_CACHE

    if not findings_data and cache_path.exists():
        try:
            findings_data = json.loads(cache_path.read_text(encoding="utf-8"))
            st.session_state.audit_result = findings_data
            st.info("Loaded previous audit from `data/cache/last_audit.json`.")
        except Exception:
            pass

    if not findings_data:
        st.warning("No audit report available. Run an audit on the 'Audit' page first.")
        if st.button("⬅️ Go to Audit"):
            set_page("Audit")
    else:
        findings = findings_data.get("findings", [])
        st.markdown(
            f"Audit for **{findings_data.get('repository', 'Unknown')}** | "
            f"Model: `{findings_data.get('model', 'agnes-3.0-flash')}` | "
            f"Total Findings: **{len(findings)}**"
        )

        col_f1, col_f2 = st.columns(2)
        with col_f1:
            severity_filter = st.multiselect(
                "Filter Severity",
                options=["high", "medium", "low", "info"],
                default=["high", "medium", "low", "info"],
            )
        with col_f2:
            pass_filter = st.multiselect(
                "Filter Audit Pass",
                options=["api_drift", "secrets_patterns", "tests"],
                default=["api_drift", "secrets_patterns", "tests"],
                format_func=lambda x: {
                    "api_drift": "API / Call-Site Drift",
                    "secrets_patterns": "Secrets / Shell Patterns",
                    "tests": "Missing Tests",
                }.get(x, x),
            )

        filtered = [
            f
            for f in findings
            if f.get("severity", "info") in severity_filter
            and f.get("pass_name", "api_drift") in pass_filter
        ]

        st.caption(f"Showing {len(filtered)} of {len(findings)} findings.")

        # Findings Summary Table
        if filtered:
            st.subheader("📊 Findings Table")
            table_records = [
                {
                    "Severity": f.get("severity", "info"),
                    "Pass": f.get("pass_name", ""),
                    "File": f.get("file", ""),
                    "Finding": f.get("title", f.get("pattern", "")),
                    "Line": f.get("line", ""),
                }
                for f in filtered
            ]
            st.dataframe(table_records, width="stretch", height=220)

            st.subheader("🔍 Finding Details")
            severity_icons = {
                "high": "🔴",
                "medium": "🟠",
                "low": "🟡",
                "info": "ℹ️",
            }

            for idx, item in enumerate(filtered, start=1):
                icon = severity_icons.get(item.get("severity"), "•")
                title = item.get("title", item.get("pattern", "Security pattern"))
                file_path = item.get("file", "Unspecified file")
                severity = item.get("severity", "info")

                with st.expander(
                    f"{icon} [{severity}] {title} — {file_path}", expanded=(severity == "high")
                ):
                    st.markdown(f"**File:** `{file_path}`")
                    st.markdown("**Evidence span:**")
                    st.code(item.get("evidence_span", "No span provided"), language="text")
                    if item.get("recommendation"):
                        st.markdown(
                            f"**Recommendation:** {item.get('recommendation', 'No recommendation')}"
                        )
        else:
            st.success("🎉 No findings match the active filters!")

        st.divider()
        st.download_button(
            "Download Findings (JSON)",
            data=json.dumps(findings_data, indent=2),
            file_name="last_audit.json",
            mime="application/json",
        )
