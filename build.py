import argparse
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from html import escape
import json
from pathlib import Path
import re
from xml.etree.ElementTree import Element, SubElement, indent, tostring

from PIL import Image, ImageDraw, ImageFont

from editorial import FORMULAS, SERIES, explanation, number, quantity, sensitivity


ROOT = Path(__file__).resolve().parent
PUBLISHED = "2026-11-21"
BRAND = "Редакция Pomonete"
PRODUCT = "https://pomonete.ru/"


@dataclass(frozen=True)
class Scenario:
    label: str
    values: tuple
    comment: str


@dataclass(frozen=True)
class Case:
    series: str
    index: int
    slug: str
    title: str
    description: str
    formula: str
    metric: str
    unit: str
    fields: tuple
    scenarios: tuple
    lead: str
    method: tuple
    trap: tuple
    followup: tuple
    counterfactual: str


def split_fields(line):
    return tuple(part.strip() for part in line.split("|"))


def read_cases():
    for file in sorted((ROOT / "cases").glob("*.txt")):
        series = file.name[:2]
        entries = re.split(r"(?m)^@\s*", file.read_text(encoding="utf-8"))[1:]
        for index, entry in enumerate(entries):
            slug, title, description, formula, a, b, c, lead, method, trap, followup, counterfactual = entry.strip().splitlines()
            model, metric, unit, *fields = split_fields(formula)
            scenarios = []
            for line in (a, b, c):
                label, operands, comment = split_fields(line)
                values = tuple(int(value) for value in operands.split())
                assert len(values) == len(fields), slug
                FORMULAS[model].evaluate(*values)
                if model in {"rate", "loss"}:
                    assert 0 <= values[0] <= values[1], slug
                scenarios.append(Scenario(label, values, comment))
            yield Case(series, index, slug, title, description, model, metric, unit, tuple(fields), tuple(scenarios),
                       lead, split_fields(method), split_fields(trap), split_fields(followup), counterfactual)


@lru_cache
def font(size, bold=False):
    candidates = [
        f"/System/Library/Fonts/Supplemental/Arial{' Bold' if bold else ''}.ttf",
        f"/usr/share/fonts/truetype/dejavu/DejaVuSans{'-Bold' if bold else ''}.ttf",
    ]
    for name in candidates:
        if Path(name).exists():
            return ImageFont.truetype(name, size)
    raise RuntimeError("Install Arial or DejaVu Sans for the Cyrillic figures.")


def fitting_font(draw, text, size, width, bold=False):
    while draw.textlength(text, font=font(size, bold)) > width:
        size -= 1
    return font(size, bold)


def draw_figure(case, path):
    small = font(22)
    width, height = 1050, 420
    surface = Image.new("RGB", (width, height), "#fffefa")
    draw = ImageDraw.Draw(surface)
    draw.text((42, 34), "POMONETE / УЧЕБНЫЙ ПРИМЕР", font=small, fill="#526555")
    draw.text((42, 80), case.metric, font=fitting_font(draw, case.metric, 37, 965, True), fill="#20251f")
    rounded = [FORMULAS[case.formula].evaluate(*row.values) for row in case.scenarios]
    low, high = min(0, *rounded), max(0, *rounded)
    span = high - low or 1
    left, track = 389, 440
    zero = left + round((0 - low) / span * track)
    for index, (scenario, value) in enumerate(zip(case.scenarios, rounded)):
        y = 154 + index * 63
        label_font = fitting_font(draw, scenario.label, 24, 324)
        draw.text((42, y + 5), scenario.label, font=label_font, fill="#20251f")
        draw.rounded_rectangle((left, y, left + track, y + 38), radius=4, fill="#e7ece2")
        extent = left + round((value - low) / span * track)
        if extent != zero:
            draw.rounded_rectangle((min(zero, extent), y, max(zero, extent), y + 38),
                                   radius=3, fill=("#365d50", "#1e4537", "#648274")[index])
        draw.line((zero, y, zero, y + 38), fill="#9aa89b", width=1)
        display = quantity(value, case.unit).replace("\u202f", " ")
        value_font = fitting_font(draw, display, 26, 162, True)
        draw.text((1005, y + 4), display, font=value_font, anchor="rt", fill="#20251f")
    draw.line((42, 365, width - 42, 365), fill="#d4ded4")
    draw.text((42, 381), "Сравнение сценариев на условных данных", font=small, fill="#586256")
    surface.save(path, optimize=True)


def url(base, leaf):
    return f"{base.rstrip('/')}/{leaf}" if base else f"./{leaf}"


def main_shell(title, description, content, canonical, metadata=None):
    article_metadata = ""
    if metadata:
        schema = json.dumps(metadata, ensure_ascii=False).replace("<", "\\u003c")
        article_metadata = f'<script type="application/ld+json">{schema}</script>'
    return f"""<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)}</title>
<meta name="description" content="{escape(description, quote=True)}">
<meta name="robots" content="index,follow,max-image-preview:large">
<link rel="canonical" href="{escape(canonical, quote=True)}">
<link rel="stylesheet" href="./styles.css">
{article_metadata}
</head>
<body>
<header class="masthead"><div class="frame"><a class="brand" href="./">Pomonete</a>
<span>Аналитика для селлеров Яндекс Маркета</span></div></header>
{content}
<footer class="footer"><div class="frame"><a href="./">Каталог разборов</a><span>{BRAND}</span></div></footer>
</body>
</html>
"""


def paragraphs(*items):
    return "\n".join(f"<p>{escape(item)}</p>" for item in items)


def heading(section):
    title, body = section
    return f"<h2>{escape(title)}</h2>\n{paragraphs(body)}"


def list_of(items):
    return "<ul>" + "".join(f"<li>{escape(item)}</li>" for item in items) + "</ul>"


def table(case):
    columns = "".join(f'<th scope="col">{escape(field)}</th>' for field in case.fields)
    rows = []
    for scenario in case.scenarios:
        metric = quantity(FORMULAS[case.formula].evaluate(*scenario.values), case.unit)
        cells = "".join(f"<td>{number(v)}</td>" for v in scenario.values)
        rows.append(f'<tr><th scope="row">{escape(scenario.label)}</th>{cells}<td><strong>{metric}</strong></td></tr>')
    return (
        '<div class="comparison"><table><caption>Три сценария</caption>'
        f'<thead><tr><th scope="col">Условие</th>{columns}<th scope="col">{escape(case.metric)}</th></tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table></div>'
    )


def link_list(cases):
    return "<ul>" + "".join(
        f'<li><a href="./{case.slug}.html">{escape(case.title)}</a></li>' for case in cases
    ) + "</ul>"


def article_content(case):
    series = SERIES[case.series]
    formula = FORMULAS[case.formula]
    method, numeric, delta, relative = explanation(case)
    simulation, effects, conclusion = sensitivity(case)
    custom_method = case.method[1]
    trap = case.trap[1]
    action = case.followup[1]
    workflow, rubric = editorial_checks(case, series)
    text = [case.lead, custom_method, method, *numeric, delta, relative, trap, workflow, series.method,
            simulation, *effects, conclusion, case.counterfactual, action, series.closing, rubric]
    image_name = f"./figures/{case.slug}.png"
    chart = (
        f'<figure><img src="{image_name}" width="1050" height="420" loading="lazy" '
        f'alt="{escape(case.metric)} по трём сценариям на условных данных">'
        '<figcaption>Иллюстрация к расчёту на условных данных.</figcaption></figure>'
    )
    return f"""
<p class="lead">{escape(case.lead)}</p>
{heading(case.method)}
{paragraphs(method)}
<p class="formula"><strong>{escape(case.metric)}</strong> = {formula.notation}</p>
{table(case)}
{chart}
{paragraphs(*numeric, delta, relative)}
{heading(case.trap)}
{paragraphs(workflow, series.method)}
<h2>Что сильнее всего меняет результат</h2>
{paragraphs(simulation)}
{list_of(effects)}
{paragraphs(conclusion, case.counterfactual)}
{heading(case.followup)}
{paragraphs(series.closing, rubric)}
""", text


def editorial_checks(case, series):
    metric = case.metric.lower()
    first, middle, third = case.scenarios
    evidence = series.evidence.lower()
    fields = ", ".join(label.lower() for label in case.fields)
    checks = [
        (
            f"Для исходной выборки пригодится такой набор материалов: {evidence}. "
            f"Зафиксируйте строки и границы периода, по которым собирался показатель «{metric}». "
            "Копию выгрузки держите рядом с рабочим расчётом. По ней коллега сможет проверить, "
            "что строку отнесли к нужному сценарию, а единица измерения сохранилась при переносе.",
            f"Оставьте в рабочей таблице причину выбора. Когда селлеры Яндекс Маркета возвращаются к расчёту "
            f"«{metric}», им пригодятся полученное значение, ответственный и дата пересмотра. "
            f"Если в решении использовался сценарий «{middle.label}», перенесите вместе с ним допущения. "
            "При обновлении источников сначала проверьте одну исходную строку и только потом пересчитывайте сводку.",
        ),
        (
            f"У сценария «{middle.label}» есть входы: {fields}. Для каждого впишите, где взять факт "
            f"и с каким временным лагом он поступит. Опорой будут {evidence}. "
            "Если один источник обновляется быстрее другого, зафиксируйте общий момент доступности. "
            "При существенном разрыве покажите последние данные отдельным оперативным значением.",
            f"Для управленческой встречи подготовьте два небольших примера из рабочих записей. Первый сверяет «{metric}» "
            f"при базовых условиях «{first.label}». Второй берёт изменившуюся строку и объясняет, какой источник исправлен. "
            "Селлеру Яндекс Маркета будет проще повторить расчёт на новой группе, если видны исходные значения, дата анализа "
            "и момент, когда итог станет достаточно точным для решения.",
        ),
        (
            f"Воспроизводимость здесь начинается с критериев включения. Отметьте, чем «{first.label}» отличается от "
            f"«{third.label}» и какие наблюдения будут отброшены в каждой строке. Как подтверждение используйте {evidence}. "
            "У неполных записей выделите одну причину. Она покажет, какие цифры ещё стоит собирать и какой объём анализа потерян.",
            f"Чтобы отделить ошибку оценки от реального изменения, после следующего отчёта соберите «{metric}» дважды. "
            "Сначала используйте исходное правило, затем замените только один предположенный вход фактическим. "
            "Так аналитика селлера Яндекс Маркета покажет, стоит ли тратить время на повторный замер или менять рабочую операцию. "
            "В итоговом отчёте сохраните обе даты проверки.",
        ),
        (
            f"Проверьте переход от первичной записи до показателя «{metric}». Колонки «{fields}» "
            "могут поступить разными путями. Пройдите пример, где дата и сумма видны в исходнике, до последней строки. "
            f"Для этого подойдут {evidence}. Затем возьмите один случай с исключением и убедитесь, "
            "что результат можно восстановить по сохранённому правилу.",
            f"При еженедельной сверке поставьте рядом сценарий «{third.label}» и реально наблюдавшееся значение. "
            "Если оценка стала систематически расходиться с результатом, назовите источник и предложите измерение меньшего масштаба. "
            "Для селлера Яндекс Маркета такой шаг важен, когда тот же показатель собирают разные сотрудники или несколько складов.",
        ),
        (
            f"Соберите небольшую исходную выборку для «{middle.label}», прежде чем переносить правило на весь магазин. "
            f"Нужны {evidence}. Среди записей найдите одну обычную и одну с изменённым значением «{case.fields[0].lower()}». "
            "Убедитесь, что после пересчёта на сопоставимое окно обе строки дают те же результаты, которые видит исполнитель. "
            "Для ручных поправок оставьте короткое основание.",
            f"Заведите карточку наблюдения с тремя числами: исходный ориентир, факт после вмешательства и размер выборки. "
            f"Для «{metric}» оставьте единицу из таблицы и дату подстановки. В аналитике продавца Яндекс Маркета "
            "показатель должен отвечать на тот же вопрос при повторном сборе. Если на следующем цикле изменятся исходники, "
            "сохраняйте расхождение вплоть до строки, которую сможет пересчитать коллега.",
        ),
    ]
    return checks[(case.index + case.index // len(checks)) % len(checks)]


def article_page(case, others, base):
    section = SERIES[case.series]
    content, text = article_content(case)
    canon = url(base, case.slug + ".html")
    metadata = {
        "@context": "https://schema.org", "@type": "Article", "headline": case.title,
        "description": case.description, "inLanguage": "ru", "datePublished": PUBLISHED,
        "image": url(base, f"figures/{case.slug}.png"),
        "author": {"@type": "Organization", "name": BRAND, "url": PRODUCT},
        "mainEntityOfPage": canon,
    }
    return main_shell(case.title, case.description, f"""
<main class="reading">
<article>
<header>
<a class="kicker" href="./#series-{case.series}">{escape(section.title)}</a>
<h1>{escape(case.title)}</h1>
<p class="dek">{escape(case.description)}</p>
<p class="byline">{BRAND} · <time datetime="{PUBLISHED}">21 ноября 2026</time> · Условные данные</p>
</header>
{content}
<p class="sources"><a href="{section.reference}">Справка Яндекс Маркета</a> ·
<a href="{PRODUCT}">Pomonete</a></p>
</article>
<aside class="related"><h2>По теме</h2>{link_list(others)}</aside>
</main>""", canon, metadata), text


def render_catalog(cases, base, companion, title, summary):
    groups = []
    for series, info in SERIES.items():
        members = [case for case in cases if case.series == series]
        if members:
            groups.append(f'<section class="group" id="series-{series}"><h2>{info.title}</h2>{link_list(members)}</section>')
    cross_link = f'<p><a href="{escape(companion, quote=True)}">Другие разборы Pomonete</a></p>' if companion else ""
    return main_shell(title, summary, f"""
<main class="frame">
<h1>{title}</h1>
<p class="dek">{summary}</p>
{cross_link}
<div class="groups">{"".join(groups)}</div>
</main>""", url(base, ""))


def sitemap(cases, base, output):
    urls = Element("urlset", xmlns="http://www.sitemaps.org/schemas/sitemap/0.9")
    for leaf in ["", *(f"{case.slug}.html" for case in cases)]:
        item = SubElement(urls, "url")
        SubElement(item, "loc").text = url(base, leaf)
        SubElement(item, "lastmod").text = PUBLISHED
    indent(urls)
    output.write_bytes(tostring(urls, encoding="utf-8", xml_declaration=True))


def quality_report(cases):
    results = []
    bags = []
    for case in cases:
        _, paragraphs_text = article_content(case)
        body = " ".join(paragraphs_text)
        count = sum(not c.isspace() for c in body)
        custom = " ".join([case.title, case.description, case.lead, *case.method, *case.trap, *case.followup,
                           case.counterfactual, *(scenario.comment for scenario in case.scenarios)])
        if "—" in custom or ";" in custom:
            raise ValueError(f"Long dash or semicolon in {case.slug}")
        words = re.findall(r"\w+", body.casefold())
        bags.append(set(zip(words, words[1:], words[2:], words[3:], words[4:])))
        results.append((count, case.slug))
    pairs = ((len(a & b) / len(a | b), cases[i].slug, cases[j].slug)
             for i, a in enumerate(bags) for j, b in enumerate(bags[:i]))
    largest_overlap = max(pairs, default=(0, "", ""))
    print(f"{len(results)} статей, {min(results)[0]}–{max(results)[0]} символов без пробелов. "
          f"Максимальное совпадение 5-грамм {largest_overlap[0]:.1%} ({largest_overlap[1]}, {largest_overlap[2]}).")
    if min(results)[0] < 5000:
        small = [item for item in results if item[0] < 5000]
        raise ValueError(f"Не хватает текста в статьях: {small}")
    if largest_overlap[0] > 0.26:
        raise ValueError(f"Требуется редактура пары {largest_overlap}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--base", default="")
    parser.add_argument("--companion", default="")
    parser.add_argument("--series", default=",".join(SERIES))
    parser.add_argument("--title", default="Считаем деньги на Яндекс Маркете")
    parser.add_argument("--summary", default="Аналитика продаж, расходы и решения на примерах с проверяемыми расчётами.")
    parser.add_argument("--partial", action="store_true", help="Build a local preview while drafting.")
    params = parser.parse_args()
    cases = list(read_cases())
    assert len({case.slug for case in cases}) == len({case.title for case in cases}) == len(cases)
    if not params.partial:
        assert Counter(case.series for case in cases) == {key: 10 for key in SERIES}
        quality_report(cases)
    if not params.output:
        return
    selected = [case for case in cases if case.series in params.series.split(",")]
    output = params.output
    figures = output / "figures"
    figures.mkdir(exist_ok=True, parents=True)
    (output / ".nojekyll").touch()
    (output / "styles.css").write_bytes((ROOT / "styles.css").read_bytes())
    catalog = render_catalog(selected, params.base, params.companion, params.title, params.summary)
    (output / "index.html").write_text(catalog, encoding="utf-8")
    for case in selected:
        others = [other for other in selected if other.series == case.series]
        others.remove(case)
        offset = sum(map(ord, case.slug)) % len(others) if others else 0
        html, _ = article_page(case, (others + others)[offset:offset + 2], params.base)
        (output / (case.slug + ".html")).write_text(html, encoding="utf-8")
        draw_figure(case, figures / (case.slug + ".png"))
    robots = "User-agent: *\nAllow: /\n"
    if params.base:
        sitemap(selected, params.base, output / "sitemap.xml")
        robots += f"Sitemap: {url(params.base, 'sitemap.xml')}\n"
    (output / "robots.txt").write_text(robots, encoding="utf-8")


if __name__ == "__main__":
    main()
