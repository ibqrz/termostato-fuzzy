#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Termostato Fuzzy (Aula 07 - Lógica Nebulosa) - Prof. Ângelo Amaral

Especificação:
  - Entrada única: temperatura T (°C)
  - Conjuntos triangulares: Fria (centro 16), Agradável (centro 22), Quente (centro 28)
  - Regras: SE Fria ENTÃO 0% | SE Agradável ENTÃO 40% | SE Quente ENTÃO 100%
  - Saída (média ponderada simples, estilo Takagi-Sugeno de ordem zero):
        P = (μF*0 + μA*40 + μQ*100) / (μF + μA + μQ)
  - Testes obrigatórios: T = 22 °C -> 40.0%  |  T = 25 °C -> 70.0%

Uso:
  python termostato_fuzzy.py                 # testes + modo interativo
  python termostato_fuzzy.py 22 25 18.5      # calcula as temperaturas dadas
  python termostato_fuzzy.py --testes        # só a bateria de testes
  python termostato_fuzzy.py --sem-ombros    # triângulos puros (sem saturar extremos)
  python termostato_fuzzy.py --sem-cor       # desativa cores ANSI

Somente biblioteca padrão (sem dependências externas).
"""

import argparse
import os
import re
import sys
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

# ----------------------------------------------------------------------------
# 1. CONFIGURAÇÃO DO TERMINAL (cores, caixas, helpers de layout)
# ----------------------------------------------------------------------------
LARGURA = 76  # largura total das caixas (em colunas)
ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


class Cor:
    """Códigos ANSI. Zerados quando a cor está desativada."""
    RESET = "\x1b[0m"
    NEGRITO = "\x1b[1m"
    DIM = "\x1b[2m"
    AZUL = "\x1b[38;5;39m"
    VERDE = "\x1b[38;5;41m"
    VERMELHO = "\x1b[38;5;203m"
    AMARELO = "\x1b[38;5;221m"
    CIANO = "\x1b[38;5;51m"
    CINZA = "\x1b[38;5;245m"

    @classmethod
    def desativar(cls):
        for nome in dir(cls):
            if nome.isupper():
                setattr(cls, nome, "")


def configurar_terminal(usar_cor: bool = True) -> None:
    """Prepara UTF-8 e ANSI (inclusive no Windows) e respeita NO_COLOR/pipes."""
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    if os.name == "nt":
        os.system("")  # habilita sequências ANSI no console do Windows 10+
    if not usar_cor or os.environ.get("NO_COLOR") or not sys.stdout.isatty():
        Cor.desativar()


def tam_visivel(texto: str) -> int:
    return len(ANSI_RE.sub("", texto))


def linha(texto: str = "", alinhar: str = "esq") -> str:
    """Uma linha dentro da caixa, com preenchimento ciente de cores ANSI."""
    interno = LARGURA - 4
    sobra = max(0, interno - tam_visivel(texto))
    if alinhar == "centro":
        esq = sobra // 2
        texto = " " * esq + texto + " " * (sobra - esq)
    else:
        texto = texto + " " * sobra
    return f"{Cor.AZUL}║{Cor.RESET} {texto} {Cor.AZUL}║{Cor.RESET}"


def topo() -> str:
    return f"{Cor.AZUL}╔{'═' * (LARGURA - 2)}╗{Cor.RESET}"


def meio(titulo: str = "") -> str:
    if not titulo:
        return f"{Cor.AZUL}╠{'═' * (LARGURA - 2)}╣{Cor.RESET}"
    rotulo = f" {titulo} "
    resto = LARGURA - 2 - len(rotulo) - 2
    return (f"{Cor.AZUL}╠══{Cor.RESET}{Cor.AMARELO}{Cor.NEGRITO}{rotulo}{Cor.RESET}"
            f"{Cor.AZUL}{'═' * resto}╣{Cor.RESET}")


def base() -> str:
    return f"{Cor.AZUL}╚{'═' * (LARGURA - 2)}╝{Cor.RESET}"


def barra(valor: float, largura: int, cor: str) -> str:
    """Barra horizontal proporcional a valor em [0, 1]."""
    cheios = int(round(max(0.0, min(1.0, valor)) * largura))
    return f"{cor}{'█' * cheios}{Cor.CINZA}{'░' * (largura - cheios)}{Cor.RESET}"


def cor_potencia(pct: float) -> str:
    if pct < 25:
        return Cor.AZUL
    if pct < 65:
        return Cor.VERDE
    return Cor.VERMELHO


# ----------------------------------------------------------------------------
# 2. MODELO FUZZY
# ----------------------------------------------------------------------------
def trimf(x: float, a: float, m: float, b: float) -> float:
    """Função de pertencimento triangular (a, m, b), conforme o slide 14."""
    if x < a or x > b:
        return 0.0
    if x == m:
        return 1.0
    if x < m:
        return (x - a) / (m - a)
    return (b - x) / (b - m)


@dataclass(frozen=True)
class ConjuntoFuzzy:
    nome: str
    a: float
    m: float          # centroide / ápice
    b: float
    potencia: float   # consequente da regra (%)
    cor: str          # nome do atributo de Cor
    ombro: Optional[str] = None  # 'esq' | 'dir' | None

    def mu(self, x: float, ombros: bool = True) -> float:
        if ombros and self.ombro == "esq" and x <= self.m:
            return 1.0
        if ombros and self.ombro == "dir" and x >= self.m:
            return 1.0
        return trimf(x, self.a, self.m, self.b)


CONJUNTOS: List[ConjuntoFuzzy] = [
    ConjuntoFuzzy("Fria",     10, 16, 22,   0.0, "AZUL",     ombro="esq"),
    ConjuntoFuzzy("Agradável", 16, 22, 28,  40.0, "VERDE"),
    ConjuntoFuzzy("Quente",   22, 28, 34, 100.0, "VERMELHO", ombro="dir"),
]

ROTULOS_ESTADO = {
    "Fria": "Desligado",
    "Agradável": "Manutenção",
    "Quente": "Arrefecimento Máximo",
}


@dataclass
class Resultado:
    temperatura: float
    pertinencias: Dict[str, float]
    numerador: float
    denominador: float
    potencia: float


def descrever_estado(mus: Dict[str, float]) -> str:
    """Rótulo do estado. Com dois conjuntos ativos mostra a transição e o peso de cada um."""
    ativos = [c for c in CONJUNTOS if mus[c.nome] > 1e-9]
    if len(ativos) == 1:
        return ROTULOS_ESTADO[ativos[0].nome]
    total = sum(mus[c.nome] for c in ativos)
    origem, destino = ativos[0], ativos[-1]
    p_o = 100 * mus[origem.nome] / total
    p_d = 100 * mus[destino.nome] / total
    return (f"{ROTULOS_ESTADO[origem.nome]} → {ROTULOS_ESTADO[destino.nome]} "
            f"({p_o:.0f}% / {p_d:.0f}%)")


def fuzzificar(t: float, ombros: bool = True) -> Dict[str, float]:
    return {c.nome: c.mu(t, ombros) for c in CONJUNTOS}


def inferir(t: float, ombros: bool = True) -> Resultado:
    """Fuzzificação + regras + média ponderada (defuzzificação TSK ordem zero)."""
    mus = fuzzificar(t, ombros)
    num = sum(mus[c.nome] * c.potencia for c in CONJUNTOS)
    den = sum(mus.values())
    if den == 0:
        raise ValueError(
            f"T = {t:g} °C está fora do universo de discurso "
            f"[{CONJUNTOS[0].a:g}, {CONJUNTOS[-1].b:g}] °C (use ombros para saturar)."
        )
    return Resultado(t, mus, num, den, num / den)


# ----------------------------------------------------------------------------
# 3. APRESENTAÇÃO
# ----------------------------------------------------------------------------
def cabecalho() -> None:
    print(topo())
    print(linha(f"{Cor.NEGRITO}{Cor.CIANO}TERMOSTATO FUZZY{Cor.RESET}", "centro"))
    print(linha(f"{Cor.CINZA}IA - Aula 07: Lógica Nebulosa e Sistemas de Decisão{Cor.RESET}", "centro"))
    print(base())


def grafico_funcoes(t: Optional[float], ombros: bool, t_min=8.0, t_max=36.0, passo=0.5) -> List[str]:
    """Gráfico ASCII das 3 funções de pertencimento com marcador da temperatura atual."""
    niveis = 8
    xs = []
    x = t_min
    while x <= t_max + 1e-9:
        xs.append(x)
        x += passo
    grade = [[" "] * len(xs) for _ in range(niveis + 1)]
    for c in CONJUNTOS:
        cor = getattr(Cor, c.cor)
        for j, xv in enumerate(xs):
            v = c.mu(xv, ombros)
            if v <= 0:
                continue
            i = int(round((1 - v) * niveis))
            grade[i][j] = f"{cor}●{Cor.RESET}"

    col_t = None
    if t is not None and t_min <= t <= t_max:
        col_t = int(round((t - t_min) / passo))

    saida = []
    for i, fileira in enumerate(grade):
        valor = 1 - i / niveis
        if col_t is not None:
            if fileira[col_t] == " ":
                fileira[col_t] = f"{Cor.AMARELO}┆{Cor.RESET}"
        rotulo = f"{Cor.CINZA}{valor:4.2f} ┤{Cor.RESET}" if i % 2 == 0 else f"{Cor.CINZA}     │{Cor.RESET}"
        saida.append(rotulo + "".join(fileira))

    eixo = f"{Cor.CINZA}     └{'─' * len(xs)}{Cor.RESET}"
    saida.append(eixo)

    # marcas do eixo X a cada 4 °C
    marcas = [" "] * (len(xs) + 3)
    textos = []
    for graus in range(int(t_min), int(t_max) + 1, 4):
        j = int(round((graus - t_min) / passo))
        textos.append((j, str(graus)))
    for j, s in textos:
        for k, ch in enumerate(s):
            marcas[j + k] = ch
    saida.append(f"{Cor.CINZA}      {''.join(marcas)} °C{Cor.RESET}")

    legenda = "   ".join(f"{getattr(Cor, c.cor)}● {c.nome}{Cor.RESET}" for c in CONJUNTOS)
    if col_t is not None:
        legenda += f"   {Cor.AMARELO}┆ T atual{Cor.RESET}"
    saida.append("      " + legenda)
    return saida


def mostrar_resultado(r: Resultado, ombros: bool, com_grafico: bool = True) -> None:
    print(topo())
    print(linha(f"{Cor.NEGRITO}Entrada:{Cor.RESET} T = {Cor.AMARELO}{Cor.NEGRITO}{r.temperatura:g} °C{Cor.RESET}"))

    # 1) Fuzzificação
    print(meio("1. FUZZIFICAÇÃO  (graus de pertencimento μ)"))
    for c in CONJUNTOS:
        mu = r.pertinencias[c.nome]
        cor = getattr(Cor, c.cor)
        print(linha(f"{cor}{c.nome:<10}{Cor.RESET} {barra(mu, 30, cor)}  μ = {Cor.NEGRITO}{mu:5.3f}{Cor.RESET}"))

    # 2) Regras
    print(meio("2. BASE DE REGRAS  (ativação concorrente)"))
    for c in CONJUNTOS:
        mu = r.pertinencias[c.nome]
        cor = getattr(Cor, c.cor)
        ativa = mu > 0
        marca = f"{Cor.VERDE}●{Cor.RESET}" if ativa else f"{Cor.CINZA}○{Cor.RESET}"
        txt = f"SE {c.nome:<9} ENTÃO Potência = {c.potencia:>5.1f}%"
        if not ativa:
            txt = f"{Cor.CINZA}{txt}{Cor.RESET}"
        else:
            txt = f"{cor}{txt}{Cor.RESET}"
        print(linha(f"{marca} {txt}   {Cor.CINZA}α = {mu:5.3f}{Cor.RESET}"))

    # 3) Defuzzificação
    print(meio("3. DEFUZZIFICAÇÃO  (média ponderada)"))
    termos = " + ".join(f"{r.pertinencias[c.nome]:.2f}×{c.potencia:g}" for c in CONJUNTOS)
    soma = " + ".join(f"{r.pertinencias[c.nome]:.2f}" for c in CONJUNTOS)
    print(linha(f"{Cor.CINZA}P = ({termos}){Cor.RESET}"))
    print(linha(f"{Cor.CINZA}    ({soma}){Cor.RESET}"))
    print(linha(f"{Cor.CINZA}  = {r.numerador:.2f} / {r.denominador:.2f}{Cor.RESET}"))

    # 4) Saída
    print(meio("SAÍDA  (comando do ar-condicionado)"))
    cp = cor_potencia(r.potencia)
    print(linha(f"Potência: {cp}{Cor.NEGRITO}{r.potencia:6.1f} %{Cor.RESET}"))
    print(linha(f"{Cor.CINZA}Estado:{Cor.RESET}   {descrever_estado(r.pertinencias)}"))
    print(linha(f"{Cor.CINZA}0%{Cor.RESET} {barra(r.potencia / 100, 62, cp)} {Cor.CINZA}100%{Cor.RESET}"))

    if com_grafico:
        print(meio("FUNÇÕES DE PERTENCIMENTO"))
        for g in grafico_funcoes(r.temperatura, ombros):
            print(linha(g))
    print(base())


def esperado_ok(obtido: float, esperado: float, tol: float = 1e-9) -> bool:
    return abs(obtido - esperado) <= tol


def rodar_testes(ombros: bool) -> bool:
    """Cada caso: (nome, T, esperado). esperado=None significa que se espera ValueError."""
    casos: List[Tuple[str, float, Optional[float]]] = [
        ("Teste 1 (obrigatório)", 22.0, 40.0),
        ("Teste 2 (obrigatório)", 25.0, 70.0),
        ("Extra: centro de Fria", 16.0, 0.0),
        ("Extra: centro de Quente", 28.0, 100.0),
        ("Extra: entre Fria e Agradável", 19.0, 20.0),
        ("Extra: entre Agradável e Quente", 24.0, 60.0),
    ]
    if ombros:
        casos += [
            ("Fora da faixa: muito frio", 5.0, 0.0),
            ("Fora da faixa: limite 10 °C", 10.0, 0.0),
            ("Fora da faixa: limite 34 °C", 34.0, 100.0),
            ("Fora da faixa: muito quente", 40.0, 100.0),
        ]
    else:
        casos += [
            ("Borda do tri. Fria (12 °C)", 12.0, 0.0),
            ("Borda do tri. Quente (32 °C)", 32.0, 100.0),
            ("Fora do universo: 5 °C", 5.0, None),
            ("Fora do universo: 40 °C", 40.0, None),
        ]

    print(topo())
    print(linha(f"{Cor.NEGRITO}BATERIA DE TESTES{Cor.RESET}", "centro"))
    print(meio())
    print(linha(f"{Cor.CINZA}{'Cenário':<32}{'T (°C)':>7}{'Esperado':>10}{'Obtido':>9}  Status{Cor.RESET}"))
    tudo_ok = True
    for nome, t, esp in casos:
        try:
            obt: Optional[float] = inferir(t, ombros).potencia
        except ValueError:
            obt = None
        if esp is None:
            ok = obt is None
            esp_txt, obt_txt = "erro", ("erro" if obt is None else f"{obt:.1f}%")
        else:
            ok = obt is not None and esperado_ok(obt, esp)
            esp_txt = f"{esp:.1f}%"
            obt_txt = "erro" if obt is None else f"{obt:.1f}%"
        tudo_ok &= ok
        status = f"{Cor.VERDE}✔ PASSOU{Cor.RESET}" if ok else f"{Cor.VERMELHO}✘ FALHOU{Cor.RESET}"
        print(linha(f"{nome:<32}{t:>7.1f}{esp_txt:>10}{obt_txt:>9}  {status}"))
    print(meio())
    resumo = (f"{Cor.VERDE}{Cor.NEGRITO}Todos os {len(casos)} testes passaram.{Cor.RESET}" if tudo_ok
              else f"{Cor.VERMELHO}{Cor.NEGRITO}Há testes com falha.{Cor.RESET}")
    print(linha(resumo))
    print(base())
    return tudo_ok


def modo_interativo(ombros: bool) -> None:
    print(f"\n{Cor.CINZA}Modo interativo: digite uma temperatura em °C (ou 'q' para sair).{Cor.RESET}")
    while True:
        try:
            bruto = input(f"{Cor.AMARELO}T (°C) ▶ {Cor.RESET}").strip().replace(",", ".")
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if bruto.lower() in {"q", "sair", "exit", ""}:
            break
        try:
            t = float(bruto)
            print()
            mostrar_resultado(inferir(t, ombros), ombros)
            print()
        except ValueError as e:
            msg = str(e)
            if msg.startswith("could not convert"):
                msg = f"'{bruto}' não é um número válido."
            print(f"{Cor.VERMELHO}Erro: {msg}{Cor.RESET}")


# ----------------------------------------------------------------------------
# 4. PROGRAMA PRINCIPAL
# ----------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description="Termostato Fuzzy (Aula 07 - Lógica Nebulosa)")
    ap.add_argument("temperaturas", nargs="*", type=float, help="temperaturas em °C a calcular")
    ap.add_argument("--testes", action="store_true", help="executa apenas a bateria de testes")
    ap.add_argument("--sem-ombros", action="store_true",
                    help="usa triângulos puros (fora de 10–34 °C não há pertencimento)")
    ap.add_argument("--sem-cor", action="store_true", help="desativa cores ANSI")
    args = ap.parse_args()

    configurar_terminal(usar_cor=not args.sem_cor)
    ombros = not args.sem_ombros

    cabecalho()
    print()
    ok = rodar_testes(ombros)

    if args.testes:
        return 0 if ok else 1

    if args.temperaturas:
        for t in args.temperaturas:
            print()
            try:
                mostrar_resultado(inferir(t, ombros), ombros)
            except ValueError as e:
                print(f"{Cor.VERMELHO}Erro: {e}{Cor.RESET}")
        return 0 if ok else 1

    # sem argumentos: demonstra os dois cenários obrigatórios e abre o modo interativo
    for t in (22.0, 25.0):
        print()
        mostrar_resultado(inferir(t, ombros), ombros)
    if sys.stdin.isatty():
        modo_interativo(ombros)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())