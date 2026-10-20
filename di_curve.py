"""
Módulo de Construção e Interpolação da Curva de Juros DI (DI1 Futuros B3)
========================================================================
Este módulo realiza a coleta de dados de mercado dos contratos futuros de DI1
da B3 e da taxa Selic/DI Over do Banco Central, calculando os prazos em dias
úteis (convenção DU/252) e aplicando diferentes métodos consagrados de
interpolação:
  1. Flat-Forward (Convenção oficial da B3 / ANBIMA)
  2. Monotone Cubic Spline (PCHIP - Piecewise Cubic Hermite Interpolating Polynomial)
  3. Cubic Spline Natural
  4. Modelo Paramétrico de Nelson-Siegel

Também calcula a estrutura a termo de taxas a termo (Forward Rates).
"""

import datetime as dt
from typing import Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd
import polars as pl
import pyield as yd
from scipy.interpolate import CubicSpline, PchipInterpolator
from scipy.optimize import curve_fit


class DICurve:
    """Representa a estrutura a termo da taxa de juros DI brasileira."""

    def __init__(
        self,
        reference_date: dt.date,
        vertices: pd.DataFrame,
        selic_over: float,
        timestamp: dt.datetime,
    ):
        self.reference_date = reference_date
        self.vertices = vertices.copy()
        self.selic_over = selic_over
        self.timestamp = timestamp

        # Arrays ordenados de DU e taxas (em decimal)
        self.du_points = self.vertices["du"].to_numpy(dtype=float)
        self.rate_points = (self.vertices["taxa"] / 100.0).to_numpy(dtype=float)

        # Ajuste prévio do Nelson-Siegel (armazenado para reutilização rápida)
        self._ns_params = None

    @classmethod
    def fetch_market_data(cls) -> "DICurve":
        """Busca dados de mercado ao vivo da B3 e do Banco Central do Brasil."""
        agora = dt.datetime.now()
        ref_date = yd.du.ultimo_dia_util()

        # 1. Taxa Over do BCB para ancorar o vértice curto (DU=1)
        try:
            selic_df = yd.selic.over_serie(ultimos=3)
            taxa_over = float(selic_df["taxa"][0])
        except Exception:
            taxa_over = 0.1365  # Fallback razoável caso a API do BCB oscile

        # 2. Cotações intradia de DI1 da B3
        df_raw = yd.b3.derivativos_intradia.derivativo_intradia("DI1")
        df_fut = df_raw.filter(pl.col("codigo_mercado") == "FUT")

        records: List[Dict] = [
            {
                "ticker": "DI Over",
                "vencimento": ref_date,
                "du": 1,
                "taxa": taxa_over * 100.0,
                "preco_ajuste_anterior": taxa_over * 100.0,
                "fonte": "BCB Over (CDI)",
                "bid": taxa_over * 100.0,
                "ask": taxa_over * 100.0,
                "contratos_abertos": 0,
                "volume_negociado": 0,
                "numero_negocios": 0,
            }
        ]

        for row in df_fut.iter_rows(named=True):
            venc = row.get("data_vencimento")
            if venc is None:
                continue

            du = yd.du.contar(ref_date, venc)
            if du is None or du <= 1:
                continue

            ult = row.get("preco_ultimo")
            bid = row.get("preco_oferta_compra")
            ask = row.get("preco_oferta_venda")
            ajuste_ant = row.get("preco_ajuste_anterior")

            # Prioridade de taxa: Último Negócio -> Mid Bid/Ask -> Ajuste Anterior
            taxa = None
            fonte = ""
            if ult is not None and not np.isnan(ult) and ult > 0:
                taxa = ult
                fonte = "Último Negócio"
            elif bid is not None and ask is not None and not (np.isnan(bid) or np.isnan(ask)) and bid > 0 and ask > 0:
                taxa = (bid + ask) / 2.0
                fonte = "Mid (Bid/Ask)"
            elif ajuste_ant is not None and not np.isnan(ajuste_ant) and ajuste_ant > 0:
                taxa = ajuste_ant
                fonte = "Ajuste Anterior"
            else:
                continue

            records.append(
                {
                    "ticker": row.get("codigo_negociacao"),
                    "vencimento": venc,
                    "du": int(du),
                    "taxa": float(taxa),
                    "preco_ajuste_anterior": float(ajuste_ant) if ajuste_ant else np.nan,
                    "fonte": fonte,
                    "bid": float(bid) if bid else np.nan,
                    "ask": float(ask) if ask else np.nan,
                    "contratos_abertos": int(row.get("contratos_abertos") or 0),
                    "volume_negociado": int(row.get("volume_negociado") or 0),
                    "numero_negocios": int(row.get("numero_negocios") or 0),
                }
            )

        df = pd.DataFrame(records)
        # Remove duplicatas de DU caso ocorram, mantendo o de maior volume
        df = df.sort_values(by=["du", "volume_negociado"], ascending=[True, False])
        df = df.drop_duplicates(subset=["du"], keep="first").reset_index(drop=True)

        return cls(
            reference_date=ref_date,
            vertices=df,
            selic_over=taxa_over,
            timestamp=agora,
        )

    def interpolate_flat_forward(self, target_dus: Union[int, float, np.ndarray, List[int]]) -> np.ndarray:
        """
        Interpolação Flat-Forward (Padrão B3 / ANBIMA).
        Assume taxa a termo constante entre vértices adjacentes.
        Equivale à interpolação linear do logaritmo do fator de capitalização:
            ln[(1 + R)^(DU/252)]
        """
        tgt = np.asarray(target_dus, dtype=float)
        # Fator de log: (DU / 252) * ln(1 + R)
        log_factors = (self.du_points / 252.0) * np.log(1.0 + self.rate_points)

        # Interpolação linear do log_factor
        interp_log_factor = np.interp(tgt, self.du_points, log_factors)

        # Reversão para taxa a.a. percentual:
        rates = np.zeros_like(tgt)
        pos = tgt > 0
        rates[pos] = (np.exp(interp_log_factor[pos] * 252.0 / tgt[pos]) - 1.0) * 100.0
        rates[~pos] = self.rate_points[0] * 100.0
        return rates

    def interpolate_pchip(self, target_dus: Union[int, float, np.ndarray, List[int]]) -> np.ndarray:
        """
        Interpolação Spline Cúbica Monótona (PCHIP - Piecewise Cubic Hermite).
        Evita 'overshooting' e oscilações espúrias que ocorrem em splines tradicionais.
        """
        tgt = np.asarray(target_dus, dtype=float)
        z_points = np.log(1.0 + self.rate_points)
        pchip = PchipInterpolator(self.du_points, z_points)
        z_interp = pchip(tgt)
        return (np.exp(z_interp) - 1.0) * 100.0

    def interpolate_cubic_spline(self, target_dus: Union[int, float, np.ndarray, List[int]]) -> np.ndarray:
        """Interpolação Spline Cúbica Natural clássica."""
        tgt = np.asarray(target_dus, dtype=float)
        z_points = np.log(1.0 + self.rate_points)
        cs = CubicSpline(self.du_points, z_points, bc_type="natural")
        z_interp = cs(tgt)
        return (np.exp(z_interp) - 1.0) * 100.0

    @staticmethod
    def _ns_formula(t: np.ndarray, beta0: float, beta1: float, beta2: float, tau: float) -> np.ndarray:
        t = np.maximum(t, 1e-5)
        ratio = t / tau
        term1 = (1.0 - np.exp(-ratio)) / ratio
        term2 = term1 - np.exp(-ratio)
        return beta0 + beta1 * term1 + beta2 * term2

    def fit_nelson_siegel(self) -> Tuple[float, float, float, float]:
        """Ajusta o modelo de Nelson-Siegel aos vértices de mercado."""
        if self._ns_params is not None:
            return self._ns_params

        t_pts = self.du_points / 252.0
        r_pts = self.rate_points

        p0 = [r_pts[-1], r_pts[0] - r_pts[-1], 0.0, 1.5]
        bounds = ([-0.5, -0.5, -0.5, 0.05], [0.5, 0.5, 0.5, 10.0])
        try:
            popt, _ = curve_fit(self._ns_formula, t_pts, r_pts, p0=p0, bounds=bounds, maxfev=5000)
            self._ns_params = tuple(popt)
        except Exception:
            # Fallback seguro
            self._ns_params = (r_pts[-1], r_pts[0] - r_pts[-1], 0.0, 1.5)
        return self._ns_params

    def interpolate_nelson_siegel(self, target_dus: Union[int, float, np.ndarray, List[int]]) -> np.ndarray:
        """Gera taxas estimadas pela curva paramétrica de Nelson-Siegel."""
        tgt = np.asarray(target_dus, dtype=float)
        params = self.fit_nelson_siegel()
        t_tgt = tgt / 252.0
        r = self._ns_formula(t_tgt, *params)
        return r * 100.0

    def calculate_forward_curve(
        self,
        grid_dus: np.ndarray,
        spot_rates_pct: np.ndarray,
        step_dus: int = 21,
    ) -> np.ndarray:
        """
        Calcula a curva de taxas forward 1M (ex: 21 dias úteis à frente).
        F(t, t + step) = [ (1 + R(t+step))^((t+step)/252) / (1 + R(t))^(t/252) ]^(252 / step) - 1
        """
        r_dec = spot_rates_pct / 100.0
        factors = (1.0 + r_dec) ** (grid_dus / 252.0)

        # Interpolação para encontrar fatores no ponto (grid_dus + step_dus)
        grid_plus = grid_dus + step_dus
        r_plus = self.interpolate_flat_forward(grid_plus) / 100.0
        factors_plus = (1.0 + r_plus) ** (grid_plus / 252.0)

        fwd_factors = factors_plus / factors
        fwd_rates = (fwd_factors ** (252.0 / step_dus) - 1.0) * 100.0
        return fwd_rates

    def generate_interpolated_grid(self, max_du: Optional[int] = None, step: int = 5) -> pd.DataFrame:
        """Gera um grid contínuo de dias úteis com todos os métodos de interpolação."""
        if max_du is None:
            max_du = int(self.du_points[-1])

        grid = np.arange(1, max_du + step, step)
        ff = self.interpolate_flat_forward(grid)
        pchip = self.interpolate_pchip(grid)
        cs = self.interpolate_cubic_spline(grid)
        ns = self.interpolate_nelson_siegel(grid)
        fwd_1m = self.calculate_forward_curve(grid, ff, step_dus=21)

        # Datas estimadas em dias úteis
        ref_ts = pd.Timestamp(self.reference_date)
        b_dates = [ref_ts + pd.offsets.CustomBusinessDay(n=int(d), holidays=[]) for d in grid]

        return pd.DataFrame(
            {
                "du": grid,
                "data_estimada": b_dates,
                "flat_forward": ff,
                "pchip": pchip,
                "cubic_spline": cs,
                "nelson_siegel": ns,
                "forward_1m": fwd_1m,
            }
        )
