"""
Dashboard Interativo e em Tempo Real da Curva de Juros DI1 (B3)
==============================================================
Desenvolvido com Streamlit e Plotly.
Atualização automática periódica, múltiplas metodologias de interpolação,
curva forward (a termo), cálculo de spread em bps vs D-1, e calculadora de taxas.

Para executar:
    streamlit run app.py
"""

import datetime as dt
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from di_curve import DICurve

# Configuração da página
st.set_page_config(
    page_title="Curva DI1 Futuros B3 | Monitor Quantitativo",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Estilização CSS customizada para visual refinado
st.markdown(
    """
    <style>
    /* Estilo geral */
    .stApp {
        background-color: #0d1117;
        color: #c9d1d9;
    }
    .metric-card {
        background-color: #161b22;
        border: 1px solid #30363d;
        border-radius: 8px;
        padding: 14px 18px;
        text-align: center;
        box-shadow: 0 4px 6px rgba(0,0,0,0.3);
    }
    .metric-card .title {
        font-size: 0.85rem;
        color: #8b949e;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    .metric-card .value {
        font-size: 1.6rem;
        color: #58a6ff;
        font-weight: 700;
        margin: 4px 0;
    }
    .metric-card .delta {
        font-size: 0.82rem;
        font-weight: 600;
    }
    .delta-positive { color: #3fb950; }
    .delta-negative { color: #f85149; }
    .delta-neutral { color: #8b949e; }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_data(ttl=10)
def load_market_curve():
    """Carrega os dados de mercado e constrói a curva."""
    return DICurve.fetch_market_data()


# Sidebar com configurações
st.sidebar.image(
    "https://upload.wikimedia.org/wikipedia/commons/thumb/c/c3/Python-logo-notext.svg/1200px-Python-logo-notext.svg.png",
    width=50,
)
st.sidebar.title("Configurações da Curva")

refresh_sec = st.sidebar.selectbox(
    "Intervalo de Auto-Refresh",
    options=[10, 15, 30, 60, 0],
    index=1,
    format_func=lambda x: f"{x} segundos" if x > 0 else "Pausado (Manual)",
)

st.sidebar.markdown("---")
st.sidebar.subheader("Modelos de Interpolação")
show_flat_fwd = st.sidebar.checkbox("Flat-Forward (Oficial B3)", value=True)
show_pchip = st.sidebar.checkbox("Monotone Spline (PCHIP)", value=True)
show_spline = st.sidebar.checkbox("Cubic Spline Natural", value=False)
show_nelson = st.sidebar.checkbox("Nelson-Siegel Paramétrico", value=True)
show_d1 = st.sidebar.checkbox("Ajuste Anterior (D-1)", value=True)
show_forward = st.sidebar.checkbox("Curva Forward 1M (21 DU)", value=False)

st.sidebar.markdown("---")
axis_choice = st.sidebar.radio(
    "Eixo Horizontal (Maturidade)",
    options=["Data de Vencimento (Anos)", "Dias Úteis (DU/252)"],
    index=0,
)

horizon_choice = st.sidebar.selectbox(
    "Foco da Curva (Zoom)",
    options=[
        "Toda a Curva (2026 - 2041)",
        "Curto Prazo (2026 - 2028 | Copom)",
        "Médio Prazo (2028 - 2032 | Ciclo)",
        "Longo Prazo (2032 - 2041 | Fiscal)",
    ],
    index=0,
)

if st.sidebar.button("🔄 Atualizar Cotações Agora", width="stretch"):
    st.cache_data.clear()
    st.rerun()


# Fragmento reativo que atualiza automaticamente
run_every_val = f"{refresh_sec}s" if refresh_sec > 0 else None


@st.fragment(run_every=run_every_val)
def render_live_dashboard():
    try:
        curve = load_market_curve()
    except Exception as e:
        st.error(f"Erro ao buscar cotações da B3: {e}")
        return

    df_v = curve.vertices
    df_grid = curve.generate_interpolated_grid(step=5)

    # Cabeçalho Principal
    col_t1, col_t2 = st.columns([3, 1])
    with col_t1:
        st.title("Curva de Juros DI1 (B3) em Tempo Real")
        st.caption(
            f"📅 Data de Referência: **{curve.reference_date.strftime('%d/%m/%Y')}** | "
            f"⏱️ Última Coleta: **{curve.timestamp.strftime('%H:%M:%S')}** | "
            f"📊 Vértices Ativos: **{len(df_v)} contratos**"
        )
    with col_t2:
        status_color = "#3fb950" if refresh_sec > 0 else "#8b949e"
        st.markdown(
            f"<div style='text-align: right; padding-top: 15px; color: {status_color}; font-weight: bold;'>"
            f"● {'Monitorando em tempo real (' + str(refresh_sec) + 's)' if refresh_sec > 0 else 'Atualização Manual'}"
            f"</div>",
            unsafe_allow_html=True,
        )

    # Cartões de Métricas Chave (Key Tenors)
    tenors = {
        "DI Over (CDI)": 1,
        "1 Ano (252 DU)": 252,
        "2 Anos (504 DU)": 504,
        "3 Anos (756 DU)": 756,
        "5 Anos (1260 DU)": 1260,
        "10 Anos (2520 DU)": 2520,
    }

    cols = st.columns(len(tenors))
    for col, (label, du_t) in zip(cols, tenors.items()):
        rate_interp = curve.interpolate_flat_forward(du_t)
        # Buscar vértice mais próximo para ver spread se houver
        idx_near = (df_v["du"] - du_t).abs().argmin()
        row_near = df_v.iloc[idx_near]
        spread_bps = (
            (row_near["taxa"] - row_near["preco_ajuste_anterior"]) * 100.0
            if pd.notna(row_near["preco_ajuste_anterior"])
            else 0.0
        )
        delta_class = "delta-positive" if spread_bps > 0 else "delta-negative" if spread_bps < 0 else "delta-neutral"
        delta_sign = "+" if spread_bps > 0 else ""

        with col:
            st.markdown(
                f"""
                <div class="metric-card">
                    <div class="title">{label}</div>
                    <div class="value">{rate_interp:.2f}%</div>
                    <div class="delta {delta_class}">
                        Δ {delta_sign}{spread_bps:.1f} bps
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.markdown("<br>", unsafe_allow_html=True)

    # Preparação dos dados para o gráfico Plotly
    x_grid = df_grid["du"] if axis_choice.startswith("Dias") else df_grid["data_estimada"]
    x_v = df_v["du"] if axis_choice.startswith("Dias") else pd.to_datetime(df_v["vencimento"])

    # Gráfico com 2 subplots: Curva de Juros e Spread em bps vs D-1
    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.08,
        subplot_titles=("Estrutura a Termo das Taxas de Juros DI1 (% a.a.)", "Variação Diária vs Ajuste Anterior (bps)"),
        row_heights=[0.72, 0.28],
    )

    # Hover template para as linhas de interpolação
    line_hover = "<b>%{fullData.name}</b><br>Data: %{x|%d/%m/%Y}<br>Taxa: %{y:.3f}%<extra></extra>" if not axis_choice.startswith("Dias") else "<b>%{fullData.name}</b><br>Prazo: %{x} DU<br>Taxa: %{y:.3f}%<extra></extra>"

    # 1. Curvas de Interpolação
    if show_flat_fwd:
        fig.add_trace(
            go.Scatter(
                x=x_grid,
                y=df_grid["flat_forward"],
                mode="lines",
                name="Flat-Forward (Padrão B3)",
                line=dict(color="#58a6ff", width=2.5),
                hovertemplate=line_hover,
            ),
            row=1,
            col=1,
        )

    if show_pchip:
        fig.add_trace(
            go.Scatter(
                x=x_grid,
                y=df_grid["pchip"],
                mode="lines",
                name="Monotone Spline (PCHIP)",
                line=dict(color="#3fb950", width=2.0, dash="dash"),
                hovertemplate=line_hover,
            ),
            row=1,
            col=1,
        )

    if show_spline:
        fig.add_trace(
            go.Scatter(
                x=x_grid,
                y=df_grid["cubic_spline"],
                mode="lines",
                name="Cubic Spline Natural",
                line=dict(color="#bc8cff", width=1.5, dash="dot"),
                hovertemplate=line_hover,
            ),
            row=1,
            col=1,
        )

    if show_nelson:
        fig.add_trace(
            go.Scatter(
                x=x_grid,
                y=df_grid["nelson_siegel"],
                mode="lines",
                name="Nelson-Siegel",
                line=dict(color="#d29922", width=1.8, dash="dot"),
                hovertemplate=line_hover,
            ),
            row=1,
            col=1,
        )

    if show_forward:
        fig.add_trace(
            go.Scatter(
                x=x_grid,
                y=df_grid["forward_1m"],
                mode="lines",
                name="Forward 1M (21 DU)",
                line=dict(color="#f0883e", width=1.8),
                hovertemplate=line_hover,
            ),
            row=1,
            col=1,
        )

    if show_d1:
        df_d1 = df_v[df_v["preco_ajuste_anterior"].notna()]
        x_d1 = df_d1["du"] if axis_choice.startswith("Dias") else pd.to_datetime(df_d1["vencimento"])
        fig.add_trace(
            go.Scatter(
                x=x_d1,
                y=df_d1["preco_ajuste_anterior"],
                mode="lines",
                name="Ajuste Anterior (D-1)",
                line=dict(color="#8b949e", width=1.3, dash="dashdot"),
                hovertemplate=line_hover,
            ),
            row=1,
            col=1,
        )

    # 2. Vértices de Mercado (Scatter com detalhes em hover)
    hover_text = []
    for _, row in df_v.iterrows():
        venc = row["vencimento"]
        ano_str = venc.strftime("%Y") if row["ticker"] != "DI Over" else "Hoje"
        venc_str = venc.strftime("%d/%m/%Y")
        anos_decorridos = row["du"] / 252.0
        delta_bps = (row["taxa"] - row["preco_ajuste_anterior"]) * 100.0 if pd.notna(row["preco_ajuste_anterior"]) else 0.0
        txt = (
            f"<b>{row['ticker']} — Ano {ano_str}</b><br>"
            f"📅 Vencimento: {venc_str}<br>"
            f"⏱️ Prazo: {row['du']} DU ({anos_decorridos:.2f} anos)<br>"
            f"📈 Taxa: <b>{row['taxa']:.3f}%</b><br>"
            f"📊 Ajuste D-1: {row['preco_ajuste_anterior']:.3f}%<br>"
            f"⚖️ Δ Spread: {delta_bps:+.1f} bps<br>"
            f"💼 Volume: {row['volume_negociado']:,} ctr<br>"
            f"📋 Abertos: {row['contratos_abertos']:,}<br>"
            f"🔍 Fonte: {row['fonte']}"
        )
        hover_text.append(txt)

    fig.add_trace(
        go.Scatter(
            x=x_v,
            y=df_v["taxa"],
            mode="markers+text",
            name="Vértices DI1 (Mercado)",
            marker=dict(
                size=8,
                color="#f85149",
                line=dict(color="#ffffff", width=1),
            ),
            hoverinfo="text",
            text=[
                f"{row['ticker']} ({row['vencimento'].strftime('%Y')})"
                if row["ticker"] in {"DI Over", "DI1F27", "DI1F28", "DI1F29", "DI1F30", "DI1F31", "DI1F33", "DI1F35", "DI1F37", "DI1F40"}
                else ""
                for _, row in df_v.iterrows()
            ],
            textposition="top center",
            textfont=dict(size=9, color="#f0f6fc"),
            hovertext=hover_text,
        ),
        row=1,
        col=1,
    )

    # 3. Subplot Inferior: Barras de Spread em bps
    df_sp = df_v[df_v["preco_ajuste_anterior"].notna()].copy()
    df_sp["spread_bps"] = (df_sp["taxa"] - df_sp["preco_ajuste_anterior"]) * 100.0
    x_sp = df_sp["du"] if axis_choice.startswith("Dias") else pd.to_datetime(df_sp["vencimento"])
    colors_bar = ["#3fb950" if s >= 0 else "#f85149" for s in df_sp["spread_bps"]]

    bar_hover = "<b>%{x|%d/%m/%Y}</b><br>Δ Spread: %{y:+.1f} bps<extra></extra>" if not axis_choice.startswith("Dias") else "<b>%{x} DU</b><br>Δ Spread: %{y:+.1f} bps<extra></extra>"

    fig.add_trace(
        go.Bar(
            x=x_sp,
            y=df_sp["spread_bps"],
            name="Δ Spread (bps)",
            marker=dict(color=colors_bar, line=dict(color="#30363d", width=0.5)),
            hovertemplate=bar_hover,
        ),
        row=2,
        col=1,
    )

    fig.add_hline(y=0, line_dash="solid", line_color="#8b949e", line_width=1, row=2, col=1)

    # Configuração de limites de zoom conforme seleção de horizonte
    x_range = None
    if horizon_choice.startswith("Curto"):
        x_range = [pd.to_datetime(curve.reference_date), pd.to_datetime("2028-07-01")] if not axis_choice.startswith("Dias") else [1, 450]
    elif horizon_choice.startswith("Médio"):
        x_range = [pd.to_datetime("2027-10-01"), pd.to_datetime("2032-07-01")] if not axis_choice.startswith("Dias") else [250, 1450]
    elif horizon_choice.startswith("Longo"):
        x_range = [pd.to_datetime("2031-10-01"), pd.to_datetime("2041-07-01")] if not axis_choice.startswith("Dias") else [1250, 3600]

    # Layout Dark Moderno do Plotly
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="#161b22",
        plot_bgcolor="#0e1117",
        font=dict(color="#c9d1d9", family="Arial, sans-serif"),
        height=680,
        margin=dict(l=60, r=40, t=50, b=40),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="center",
            x=0.5,
            bgcolor="rgba(22, 27, 34, 0.8)",
            bordercolor="#30363d",
            borderwidth=1,
        ),
        hovermode="x unified",
    )

    fig.update_yaxes(title_text="Taxa (% a.a.)", tickformat=".2f", row=1, col=1, gridcolor="#30363d")
    fig.update_yaxes(title_text="Δ Spread (bps)", tickformat="+.0f", row=2, col=1, gridcolor="#30363d")
    fig.update_xaxes(gridcolor="#30363d")

    if not axis_choice.startswith("Dias"):
        fig.update_xaxes(
            title_text="Ano de Vencimento do Contrato",
            dtick="M12",
            tickformat="%Y",
            range=x_range,
            row=2,
            col=1,
        )
        fig.update_xaxes(
            dtick="M12",
            tickformat="%Y",
            range=x_range,
            row=1,
            col=1,
        )
    else:
        fig.update_xaxes(title_text="Prazo em Dias Úteis (DU/252)", range=x_range, row=2, col=1)
        fig.update_xaxes(range=x_range, row=1, col=1)

    st.plotly_chart(fig, width="stretch")

    # Seção Inferior: Calculadora de Interpolação e Tabela de Vértices
    tab1, tab2, tab3 = st.tabs(["🧮 Calculadora de Taxas Interpoladas", "📋 Tabela de Vértices DI1", "📐 Metodologias"])

    with tab1:
        st.subheader("Interpolar Taxa para Prazos Específicos")
        col_c1, col_c2, col_c3 = st.columns([1, 1, 2])
        with col_c1:
            input_mode = st.radio("Entrada por:", ["Dias Úteis (DU)", "Data Futura"])

        if input_mode == "Dias Úteis (DU)":
            with col_c2:
                target_du = st.number_input("Dias Úteis Alvo:", min_value=1, max_value=5000, value=126, step=21)
        else:
            with col_c2:
                target_date = st.date_input("Data de Vencimento Alvo:", value=dt.date.today() + dt.timedelta(days=180))
                target_du = yd.du.contar(curve.reference_date, target_date)
                st.caption(f"Dias Úteis calculados: **{target_du} DU**")

        with col_c3:
            if target_du and target_du > 0:
                ff_val = curve.interpolate_flat_forward(target_du)
                pchip_val = curve.interpolate_pchip(target_du)
                ns_val = curve.interpolate_nelson_siegel(target_du)
                pu = 100000.0 / ((1.0 + ff_val / 100.0) ** (target_du / 252.0))

                st.markdown(
                    f"""
                    <div style="background-color: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 15px;">
                        <h4 style="color: #58a6ff; margin-top: 0;">Resultado para DU = {target_du}:</h4>
                        <ul style="list-style: none; padding-left: 0; line-height: 1.8;">
                            <li>🔹 <b>Flat-Forward (B3):</b> <span style="color:#58a6ff; font-weight:bold;">{ff_val:.4f}% a.a.</span></li>
                            <li>🔹 <b>Monotone Spline (PCHIP):</b> <span style="color:#3fb950; font-weight:bold;">{pchip_val:.4f}% a.a.</span></li>
                            <li>🔹 <b>Nelson-Siegel:</b> <span style="color:#d29922; font-weight:bold;">{ns_val:.4f}% a.a.</span></li>
                            <li>💰 <b>PU Teórico (Base R$ 100k):</b> <span style="color:#f0f6fc; font-weight:bold;">R$ {pu:,.2f}</span></li>
                        </ul>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

    with tab2:
        st.subheader("Cotações e Dados Cadastrais dos Contratos Futuros DI1")
        df_display = df_v[
            [
                "ticker",
                "vencimento",
                "du",
                "taxa",
                "preco_ajuste_anterior",
                "bid",
                "ask",
                "volume_negociado",
                "contratos_abertos",
                "fonte",
            ]
        ].copy()
        df_display["spread_bps"] = (df_display["taxa"] - df_display["preco_ajuste_anterior"]) * 100.0
        df_display.columns = [
            "Ticker",
            "Vencimento",
            "DU",
            "Taxa Atual (%)",
            "Ajuste D-1 (%)",
            "Bid (%)",
            "Ask (%)",
            "Volume (ctr)",
            "Abertos (ctr)",
            "Fonte da Taxa",
            "Δ bps",
        ]

        st.dataframe(
            df_display.style.format(
                {
                    "Taxa Atual (%)": "{:.3f}%",
                    "Ajuste D-1 (%)": "{:.3f}%",
                    "Bid (%)": "{:.3f}%",
                    "Ask (%)": "{:.3f}%",
                    "Δ bps": "{:+.1f}",
                    "Volume (ctr)": "{:,.0f}",
                    "Abertos (ctr)": "{:,.0f}",
                }
            ),
            width="stretch",
            height=400,
        )

        csv = df_display.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="📥 Exportar Vértices para CSV",
            data=csv,
            file_name=f"curva_di1_{curve.reference_date.strftime('%Y%m%d')}.csv",
            mime="text/csv",
        )

    with tab3:
        st.markdown(
            """
            ### Fundamentos da Interpolação no Mercado Brasileiro
            
            1. **Convenção de Contagem de Prazo:** 
               - Dias úteis brasileiros (`DU / 252`), apurados de acordo com o calendário da B3 e ANBIMA.
               - Regime de juros compostos exponenciais: $(1 + R)^{DU / 252}$.
            
            2. **Método Flat-Forward (Padrão Oficial B3):**
               - Assume que a taxa a termo entre dois vértices adjacentes $(t_1, t_2)$ permanece constante:
                 $$(1 + F_{1,2}) = \\left[ \\frac{(1 + R_2)^{t_2 / 252}}{(1 + R_1)^{t_1 / 252}} \\right]^{\\frac{252}{t_2 - t_1}}$$
               - Garante que a curva não gera oportunidades de arbitragem em contratos futuros a termo.
               
            3. **Monotone Cubic Spline (PCHIP):**
               - Spline cúbica que preserva a monotonicidade local dos dados, eliminando o efeito de 'overshooting' (oscilações espúrias que ocorrem com splines cúbicas comuns).
               
            4. **Modelo de Nelson-Siegel:**
               - Modelo paramétrico padrão de bancos centrais que divide a curva em Nível (Level $\\beta_0$), Inclinação (Slope $\\beta_1$) e Curvatura (Curvature $\\beta_2$).
            """
        )


render_live_dashboard()
