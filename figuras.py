"""Figuras SVG produzidas apenas com a biblioteca padrão."""
from __future__ import annotations

from pathlib import Path

def _svg_header(width: int, height: int) -> list[str]:
    return [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        '<g font-family="Arial, sans-serif" fill="#20242b">',
    ]


def write_convergence(path: Path, runs: list) -> None:
    """Cinco curvas de melhor solução factível acumulada em um SVG."""
    width, height = 900, 480
    max_evaluations = max(run.evaluations for run in runs)
    left, top, right, bottom = 75, 55, 55, 75
    values = [value for run in runs for _, value in run.trace]
    if not values:
        raise ValueError("Nenhuma curva factível para desenhar")
    low, high = min(values), max(values)
    if high == low:
        high = low + max(1.0, abs(low) * 0.01)
    x = lambda step: left + (step - 1) / max(1, max_evaluations - 1) * (width - left - right)
    y = lambda value: top + (high - value) / (high - low) * (height - top - bottom)
    lines = _svg_header(width, height)
    title = ("Custo", "Desvio SiO2", "Desvio Al2O3")[runs[0].objective]
    lines.append(f'<text x="75" y="30" font-size="20" font-weight="bold">Convergência: {title}</text>')
    unit = "R$ milhões" if runs[0].objective == 0 else "pp²"
    lines.append(f'<text x="845" y="30" text-anchor="end" font-size="12">{unit}</text>')
    lines.append(f'<path d="M {left} {top} V {height-bottom} H {width-right}" fill="none" stroke="#444"/>')
    for tick in range(5):
        value = low + (high - low) * tick / 4
        yy = y(value)
        lines.append(f'<path d="M {left} {yy:.1f} H {width-right}" stroke="#e5e7eb"/>')
        shown = value / 1_000_000 if runs[0].objective == 0 else value
        lines.append(f'<text x="{left-8}" y="{yy+4:.1f}" text-anchor="end" font-size="12">{shown:.2f}</text>')
    for tick in range(5):
        step = 1 + (max_evaluations - 1) * tick // 4
        xx = x(step)
        lines.append(f'<text x="{xx:.1f}" y="{height-bottom+22}" text-anchor="middle" font-size="12">{step}</text>')
    colors = ("#2563eb", "#e11d48", "#059669", "#9333ea", "#d97706")
    for run, color in zip(runs, colors):
        if not run.trace:
            continue
        points = [(step, value) for step, value in run.trace]
        commands = [f'M {x(points[0][0]):.1f} {y(points[0][1]):.1f}']
        for step, value in points[1:]:
            commands.append(f'H {x(step):.1f} V {y(value):.1f}')
        commands.append(f'H {x(run.evaluations):.1f}')
        lines.append(f'<path d="{" ".join(commands)}" fill="none" stroke="{color}" stroke-width="2"/>')
        legend_x = 105 + (run.number - 1) * 150
        lines.append(f'<path d="M {legend_x} 440 h 22" stroke="{color}" stroke-width="3"/>')
        lines.append(f'<text x="{legend_x+27}" y="444" font-size="12">Execução {run.number}</text>')
    lines.append('<text x="450" y="476" text-anchor="middle" font-size="13">Avaliações de soluções candidatas</text>')
    lines.append('</g></svg>')
    path.write_text("\n".join(lines), encoding="utf-8")


def write_solution(path: Path, problem, run) -> None:
    """Mapa de caminhões por minério/pilha, com os dois teores ao lado."""
    assert run.best_plan is not None and run.best_evaluation is not None
    width, height = 1200, 470
    x0, y0, cell_w, cell_h = 100, 110, 42, 27
    lines = _svg_header(width, height)
    names = ("Custo", "Desvio SiO2", "Desvio Al2O3")
    lines.append(f'<text x="60" y="34" font-size="21" font-weight="bold">Melhor plano: {names[run.objective]}</text>')
    values = run.best_evaluation.objectives
    lines.append(f'<text x="60" y="59" font-size="13">Custo: R$ {values[0]:,.0f}   |   Soma SiO2: {values[1]:.4f} pp²   |   Soma Al2O3: {values[2]:.4f} pp²</text>')
    for i in range(len(problem.ores)):
        xx = x0 + i * cell_w
        lines.append(f'<text x="{xx+cell_w/2:.1f}" y="98" text-anchor="middle" font-size="11">M{i+1}</text>')
    lines.append('<text x="962" y="98" font-size="11">SiO2 %</text>')
    lines.append('<text x="1050" y="98" font-size="11">Al2O3 %</text>')
    for p, row in enumerate(run.best_plan):
        yy = y0 + p * cell_h
        counts = [row.count(i) for i in range(len(problem.ores))]
        lines.append(f'<text x="60" y="{yy+18}" font-size="12">P{p+1}</text>')
        for i, amount in enumerate(counts):
            shade = min(235, 35 * amount)
            color = f'rgb({245-shade//3},{250-shade//5},{255-shade//12})'
            xx = x0 + i * cell_w
            lines.append(f'<rect x="{xx}" y="{yy}" width="{cell_w-1}" height="{cell_h-1}" fill="{color}" stroke="#d1d5db"/>')
            if amount:
                lines.append(f'<text x="{xx+cell_w/2:.1f}" y="{yy+18}" text-anchor="middle" font-size="12">{amount}</text>')
        lines.append(f'<text x="962" y="{yy+18}" font-size="12">{run.best_evaluation.si[p]:.3f}</text>')
        lines.append(f'<text x="1050" y="{yy+18}" font-size="12">{run.best_evaluation.al[p]:.3f}</text>')
        if p == 4:
            lines.append(f'<path d="M 50 {yy+cell_h+1} H 1135" stroke="#20242b" stroke-width="2"/>')
    lines.append('<text x="60" y="420" font-size="12">Cada célula indica o número de caminhões de um minério na pilha. P1–P5: Sinter 1; P6–P10: Sinter 2.</text>')
    lines.append('</g></svg>')
    path.write_text("\n".join(lines), encoding="utf-8")
