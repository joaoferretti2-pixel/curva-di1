# Monitor e Interpolação da Curva de Juros DI1 (B3)

Aplicação profissional em Python para coleta de dados de mercado da **B3** e **Banco Central**, cálculo dos prazos na convenção brasileira de contagem de dias úteis (**DU/252**) e **interpolação da estrutura a termo das taxas de juros (Curva Pré)** com **atualização automática em tempo real**.

---

## 🚀 Como Executar

Você tem duas formas prontas para visualizar a curva atualizando automaticamente:

### 1. Dashboard Interativo Web (Streamlit + Plotly)
Ideal para análise aprofundada, alternar entre métodos de interpolação, inspecionar contratos com hover, calcular taxas para prazos customizados e exportar para CSV:

```bash
streamlit run app.py
```
*Acesse no navegador:* `http://localhost:8501`

**Recursos do Dashboard:**
- 🔄 **Auto-Refresh reativo** configurável (10s, 15s, 30s, 60s ou manual).
- 📊 **Comparação de Modelos:** Flat-Forward (B3), Monotone Spline (PCHIP), Cubic Spline, Nelson-Siegel e Curva Forward 1M.
- 📉 **Painel de Spread ($\Delta$ bps):** Comparação em tempo real com o Ajuste Anterior ($D-1$) da B3.
- 🧮 **Calculadora de Taxa Teórica:** Informe qualquer quantidade de dias úteis ou data futura e obtenha a taxa interpolada e o Preço Unitário (PU).
- 📋 **Tabela de Vértices Ativos:** Contratos DI1 com cotação atual, bid, ask, volume, contratos em aberto e botão de download em CSV.

---

### 2. Janela Desktop Nativa com Atualização Automática (Matplotlib FuncAnimation)
Se você prefere uma janela gráfica desktop leve que atualiza a cada 15 segundos:

```bash
python live_chart.py
```

Você também pode personalizar o intervalo de atualização (em segundos):
```bash
python live_chart.py --intervalo 30
```

---

## 📐 Metodologias e Convenções de Mercado

1. **Convenção de Dias Úteis (DU/252):**
   - Utiliza o calendário oficial de feriados nacionais da B3 e ANBIMA através da biblioteca `pyield`.
   - Fator de capitalização:
     $$(1 + R)^{DU / 252}$$

2. **Vértice Curto (DU = 1):**
   - Ancorado na taxa Selic/DI Over apurada pelo Banco Central do Brasil.

3. **Flat-Forward (Convenção Oficial B3 / ANBIMA):**
   - Assume taxa a termo constante entre vértices adjacentes. Equivale à interpolação linear do logaritmo do fator de acumulação:
     $$\ln\left[(1 + R)^{DU/252}\right]$$
   - Garante a ausência de oportunidades de arbitragem na curva a termo.

4. **Monotone Cubic Spline (PCHIP):**
   - Spline cúbica com preservação de monotonicidade local. Elimina oscilações indesejadas (*overshooting*) comuns em splines cúbicas naturais.

5. **Modelo Paramétrico de Nelson-Siegel:**
   - Decompõe a curva em três fatores econômicos: Nível ($\beta_0$), Inclinação ($\beta_1$) e Curvatura ($\beta_2$).

6. **Curva a Termo (Forward Rates):**
   - Taxa a termo de 1 mês (21 dias úteis à frente) para identificar as expectativas implícitas do mercado sobre decisões do COPOM.

---

## 📁 Estrutura dos Arquivos

| Arquivo | Descrição |
| :--- | :--- |
| `di_curve.py` | Módulo quantitativo com a classe `DICurve`, coleta de dados B3/BCB e algoritmos de interpolação. |
| `app.py` | Dashboard completo em Streamlit com gráficos interativos em Plotly e atualização em tempo real. |
| `live_chart.py` | Script com animação automática em Matplotlib (janela desktop). |
| `requirements.txt` | Lista de bibliotecas utilizadas. |

---

## 📦 Bibliotecas Utilizadas

- `pyield`: Coleta de derivativos B3, taxas Selic/BCB e cálculo de dias úteis com calendário nacional.
- `polars` & `pandas`: Processamento vetorial e manipulação de séries temporais financeiras.
- `numpy` & `scipy`: Otimização, regressão não-linear (Nelson-Siegel) e algoritmos de interpolação (`PchipInterpolator`, `CubicSpline`).
- `streamlit` & `plotly`: Interface web reativa e gráficos financeiros interativos.
- `matplotlib`: Renderização do monitor gráfico desktop com `FuncAnimation`.
