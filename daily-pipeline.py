#!/usr/bin/env python3
"""Bravo Quinté Daily Pipeline — met à jour tout le site en une commande."""
import argparse, json, os, re, sys, subprocess
from datetime import datetime

def load_chevaux(raw):
    if raw.startswith('@'):
        with open(raw[1:], encoding='utf-8') as f: return json.load(f)
    return json.loads(raw)

def update_index_html(repo, a):
    fp = os.path.join(repo, 'index.html')
    with open(fp, encoding='utf-8') as fh: c = fh.read()
    ch = load_chevaux(a.chevaux)
    sel = a.selection.split(','); top = a.top5.split(',')

    # video
    c = re.sub(r'youtu\.be/[A-Za-z0-9_-]{11}', f'youtu.be/{a.video}', c)
    c = re.sub(r'img\.youtube\.com/vi/[A-Za-z0-9_-]{11}', f'img.youtube.com/vi/{a.video}', c)

    # chevaux JS
    parts = []
    for num in sorted(int(k) for k in ch):
        h = ch[str(num)]
        e = f'{{num:{num},nom:"{h["nom"]}",driver:"{h.get("driver","—")}",entraineur:"{h.get("entraineur","—")}",musique:"{h.get("musique","—")}",cote:"{h.get("cote","—")}"'
        if h.get('statut'): e += f',statut:"{h["statut"]}",cls:"{h["cls"]}"'
        e += '}'; parts.append(e)
    c = re.sub(r'var chevaux=\[.*?\];', 'var chevaux=[' + ','.join(parts) + '];', c, flags=re.S)

    # selection, top5, base
    c = re.sub(r'var selection=\[[^\]]*\];', f'var selection=[{",".join(sel)}];', c)
    c = re.sub(r'var top5=\[[^\]]*\];', f'var top5=[{",".join(top)}];', c)
    c = re.sub(r'c\.num===\d+', f'c.num==={a.base}', c)

    # quinté section title
    c = re.sub(r"<h1 class='font-display'[^>]*>[^<]*&#8212; Quinté\+</h1>",
               f"<h1 class='font-display' style='font-size:2.5rem;color:#0f172a;margin:0 0 .5rem;'>{a.course} &#8212; Quinté+</h1>", c)
    c = re.sub(r"<h1 class='font-display'[^>]*>Pronostic Quinté.*?</h1>",
               f"<h1 class='font-display' style='font-size:2.5rem;margin:0 0 1rem;'>Pronostic Quinté {a.hippo} {a.date_disp}</h1>", c)
    # description
    c = re.sub(r"<p style='color:#475569;margin:0 0 2rem;'>[^<]*&#8226;[^<]*</p>",
               f"<p style='color:#475569;margin:0 0 2rem;'>{a.hippo} &#8226; {a.discipline} &#8226; {a.dist} &#8226; Corde à droite &#8226; {a.partants} partants</p>", c)
    # KPI cards (kpi-card structure)
    for label, val in [('Hippodrome', a.hippo), ('Type', a.discipline), ('Distance', a.dist), ('Allocation', f'{a.dotation} &#8364;')]:
        pat = f"<div class='kpi-card'><p class='kpi-label'>{label}</p><p class='kpi-value'>[^<]*</p></div>"
        rep = f"<div class='kpi-card'><p class='kpi-label'>{label}</p><p class='kpi-value'>{val}</p></div>"
        c = re.sub(pat, rep, c)

    # static fallback: partants table
    rows = []
    for num in sorted(int(k) for k in ch):
        h = ch[str(num)]
        st = f'<td><span class="{h["cls"]}">{h["statut"]}</span></td>' if h.get('statut') else '<td>&#8212;</td>'
        rows.append(f'<tr><td>{num}</td><td>{h["nom"]}</td><td>{h.get("driver","—")}</td><td>{h.get("entraineur","—")}</td><td>{h.get("cote","—")}</td>{st}</tr>')
    c = re.sub(r"<tbody id='partants-tbody'>.*?</tbody>", "<tbody id='partants-tbody'>\n" + '\n'.join(rows) + "\n</tbody>", c, flags=re.S)

    # static fallback: top5
    t5 = '\n'.join(f'<li><strong>{n}</strong> - {ch.get(n,ch.get(int(n),{})).get("nom","?")}</li>' for n in top)
    c = re.sub(r"(<h2[^>]*>Top 5</h2>\s*<ul id='top5-list'>).*?(</ul>)", f'\\1\n{t5}\\2', c, flags=re.S)

    # static fallback: selection
    sl = '\n'.join(f'<li><strong>{n}</strong> - {ch.get(n,ch.get(int(n),{})).get("nom","?")}{" (BASE)" if int(n)==a.base else ""}</li>' for n in sel)
    c = re.sub(r"(<ul id='selection-list'>).*?(</ul>)", f'\\1\n{sl}\\2', c, flags=re.S)

    # static fallback: tickets
    c = re.sub(r'<code>Base \d+ / [^<]*</code>', f'<code>Base {a.base} / {",".join(sel)}</code>', c)
    c = re.sub(r'<code>\d+ - \d+ - \d+</code>', f'<code>{" — ".join(sel[:3])}</code>', c)
    c = re.sub(r'<code>\d+ - \d+ - \d+ - \d+ - \d+</code>', f'<code>{" — ".join(sel[:5])}</code>', c)
    c = re.sub(r'<code>\d+(?: - \d+){7}</code>', f'<code>{" — ".join(sel)}</code>', c)

    # archives
    if a.hippo not in c:
        c = c.replace('var archives=[', f'var archives=[{{date:"{a.date}",hippo:"{a.hippo}",course:"{a.course}"}},')

    with open(fp, 'w', encoding='utf-8', newline='') as fh: fh.write(c)
    print(f"  index.html: video={a.video}, base={a.base}, {len(ch)} partants")

def build_tickets(sel, base):
    """Genere les tickets depuis la selection avec couts reels."""
    import math
    base_s = str(base)
    pet = [base_s] + [x for x in sel[:3] if x != base_s][:2]
    cp = ' / '.join(pet)
    qj = ' &#8212; '.join(sel[:5])
    n = len(sel)
    nb_comb = math.ceil(math.comb(n,4)/4) + math.ceil(math.comb(n,5)/5) + math.ceil(math.comb(n,6)/6)
    multi_cost = nb_comb * 2
    article = f'''<h2>Tickets</h2>
<div class="ticket"><h4>Petit budget (&#8776;5 &#8364;)</h4><p>Couplé placé : <strong>{cp}</strong></p><p>3 tickets &#215; 1,50 &#8364; = 4,50 &#8364;</p></div>
<div class="ticket"><h4>Budget moyen (&#8776;15 &#8364;)</h4><p>Quinté+ simple : <strong>{qj}</strong></p><p>1 ticket &#215; 2,00 &#8364; + couplés = &#8776;15 &#8364;</p></div>
<div class="ticket"><h4>Ambitieux (&#8776;{multi_cost} &#8364;)</h4><p>Multi 4/5/6 : <strong>{' &#8212; '.join(sel)}</strong></p><p>{nb_comb} tickets &#215; 2,00 &#8364; &#8776; {multi_cost} &#8364;</p></div>'''
    return article

def build_analyse(a, ch, sel, top):
    """Bloc Notre Analyse en prose genere depuis les donnees."""
    base_n = str(a.base)
    bh = ch.get(base_n, {})
    bn = bh.get('nom', '?'); bd = bh.get('driver', '?'); bc = bh.get('cote', '?')
    out_clean = [n for n in sel if str(n) != base_n and n not in (sel[0], sel[1], sel[2])]
    if out_clean:
        out_name = ch.get(out_clean[0], {}).get('nom', '?')
        out_cote = ch.get(out_clean[0], {}).get('cote', '?')
    else:
        out_name, out_cote = '—', '—'
    prem = ch.get(sel[0], {}); prem_n = prem.get('nom', '?'); prem_c = prem.get('cote', '?')
    third_h = ch.get(sel[2], {}); third_n = third_h.get('nom', '?'); third_c = third_h.get('cote', '?')
    return f'''<h2>Notre analyse</h2>
<div class="card">
<p><strong>Le scénario.</strong> Ce Quinté+ réunit {a.partants} partants sur {a.dist} mètres. Nous construisons notre sélection autour d'une paire qui nous semble nettement au-dessus du lot, puis nous élargissons à cinq pour couvrir les profils de valeur.</p>
<p><strong>Pourquoi la base.</strong> Notre favori {bn} (n°{base_n}) s'appuie sur une forme régulière et des moyens confirmés. Associé à {bd}, sur une distance qui correspond à ses aptitudes ({a.discipline} à {a.hippo}), il coche les cases de la réussite et son prix ({bc}/1) reste jouable. À ses côtés, {prem_n} (n°{sel[0]}, {prem_c}/1) offre une seconde cartouche.</p>
<p><strong>Ce qui invaliderait notre base.</strong> En cas de terrain sélectif ou d'un départ trop lent, {bn} pourrait se retrouver nez au vent. Le vrai danger viendrait de {third_n} (n°{sel[2]}, {third_c}/1).</p>
<p><strong>L'outsider de valeur.</strong> Côté surprise, nous suivons {out_name} (n°{out_clean[0]}, {out_cote}/1). Sa cote sous-estime sa récente sortie ; sur sa meilleure valeur, il est loin de faire tapis à ce prix.</p>
</div>'''

def create_article(repo, a, date_disp):
    ch = load_chevaux(a.chevaux); sel = a.selection.split(','); top = a.top5.split(',')
    driver_col = "Driver" if "Trot" in a.discipline else "Jockey"
    rows = []
    for num in sorted(int(k) for k in ch):
        h = ch[str(num)]
        cls = ' class="base"' if num==a.base else (' class="selection"' if num in [int(x) for x in sel] else '')
        rows.append(f'<tr{cls}><td>{num}</td><td>{h["nom"]}</td><td>{h.get("driver","—")}</td><td>{h.get("cote","—")}</td></tr>')
    badges = ''.join(f'<span class="badge">{n}</span>' for n in sel)
    labels = ['Notre favori','2ème','3ème','4ème','5ème']
    top5 = '\n'.join(f'<p><strong>{labels[i]} :</strong> {n} &#8212; {ch.get(n,ch.get(int(n),{})).get("nom","?")}</p>' for i,n in enumerate(top))
    tickets = build_tickets(sel, a.base)
    analyse = build_analyse(a, ch, sel, top)

    html = f'''<!DOCTYPE html>
<html lang="fr"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Pronostic Quinté {a.hippo} {date_disp} - {a.course}</title>
<meta name="description" content="Pronostic gratuit quinté {a.hippo} {date_disp} : {a.course}. Analyse, sélection, top 5 et tickets.">
<link rel="canonical" href="https://bravoquinte.github.io/bravoquinte/{a.slug}.html">
<meta property="og:type" content="article"/>
<meta property="og:title" content="Pronostic Quinté {a.hippo} {date_disp} - {a.course}"/>
<meta property="og:description" content="Pronostic gratuit quinté {a.hippo} {date_disp} : {a.course}. Analyse, sélection, top 5 et tickets."/>
<meta property="og:url" content="https://bravoquinte.github.io/bravoquinte/{a.slug}.html"/>
<meta property="og:image" content="https://bravoquinte.github.io/bravoquinte/{a.image}"/>
<meta property="og:locale" content="fr_FR"/>
<meta name="twitter:card" content="summary_large_image"/>
<meta name="twitter:title" content="Pronostic Quinté {a.hippo} {date_disp} - {a.course}"/>
<meta name="twitter:image" content="https://bravoquinte.github.io/bravoquinte/{a.image}"/>
<script type="application/ld+json">
{{"@context":"https://schema.org","@type":"BreadcrumbList","itemListElement":[{{"@type":"ListItem","position":1,"name":"Accueil","item":"https://bravoquinte.github.io/bravoquinte/"}},{{"@type":"ListItem","position":2,"name":"Pronostic {a.hippo}","item":"https://bravoquinte.github.io/bravoquinte/{a.slug}.html"}}]}}
</script>
<script type="application/ld+json">
{{"@context":"https://schema.org","@type":"BlogPosting","headline":"Pronostic Quinté {a.hippo} {date_disp} - {a.course}","description":"Pronostic gratuit quinté {a.hippo} {date_disp} : {a.course}. Analyse, sélection, top 5 et tickets.","datePublished":"{a.date}T08:00:00+00:00","author":{{"@type":"Organization","name":"Bravo Quinté"}},"publisher":{{"@type":"Organization","name":"Bravo Quinté","logo":{{"@type":"ImageObject","url":"https://bravoquinte.github.io/bravoquinte/images/logo.png"}}}},"image":"https://bravoquinte.github.io/bravoquinte/{a.image}","mainEntityOfPage":{{"@type":"WebPage","@id":"https://bravoquinte.github.io/bravoquinte/{a.slug}.html"}}}}
</script>
<style>:root{{--primary:#16a34a;--primary-dark:#15803d;--dark:#0f172a;--gray:#64748b;--border:#e2e8f0}}*{{box-sizing:border-box}}body{{font-family:'Inter',system-ui,sans-serif;margin:0;padding:0;color:var(--dark);background:#fff;line-height:1.6}}.container{{max-width:800px;margin:0 auto;padding:1rem}}h1{{font-size:2rem;margin:1rem 0}}h2{{font-size:1.5rem;margin:2rem 0 1rem;border-bottom:2px solid var(--primary);padding-bottom:.5rem}}.meta{{color:var(--gray);font-size:.9rem;margin-bottom:1.5rem}}.badge{{display:inline-block;background:#dcfce7;color:#15803d;font-size:.75rem;font-weight:700;padding:.25rem .5rem;border-radius:9999px;margin-right:.5rem}}.card{{background:#f8fafc;border:1px solid var(--border);border-radius:12px;padding:1.5rem;margin:1rem 0}}.kpi{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:1rem;margin:1rem 0}}.kpi-item{{text-align:center;padding:1rem;background:#fff;border:1px solid var(--border);border-radius:12px}}.kpi-label{{font-size:.75rem;text-transform:uppercase;color:var(--gray);margin:0}}.kpi-value{{font-size:1.5rem;font-weight:700;color:var(--primary);margin:.25rem 0}}table{{width:100%;border-collapse:collapse;margin:1rem 0;font-size:.9rem}}th{{background:var(--dark);color:#fff;padding:.75rem;text-align:left}}td{{padding:.75rem;border-bottom:1px solid var(--border)}}tr:nth-child(even){{background:#f8fafc}}.base{{background:#dcfce7;font-weight:700}}.selection{{background:#fef3c7}}.ticket{{background:#f0fdf4;border:2px solid var(--primary);border-radius:8px;padding:1rem;margin:.5rem 0}}.ticket h4{{margin:0 0 .5rem;color:var(--primary)}}.btn{{display:inline-block;background:var(--primary);color:#fff;padding:.75rem 1.5rem;border-radius:8px;text-decoration:none;font-weight:600;margin:.5rem 0}}a{{color:var(--primary)}}.post-img{{max-width:100%;height:auto;border-radius:12px;border:1px solid var(--border);margin:1.5rem 0;display:block}}</style></head><body>
<div class="container">
<h1>Pronostic Quinté {a.hippo} {date_disp}</h1>
<p class="meta"><span class="badge">Quinté du jour</span><span class="badge">Gratuit</span>Publié le {date_disp}</p>
<img src="{a.image}" alt="Pronostic Quinté {a.hippo} {a.course}" class="post-img">
<div class="card"><h2>{a.course} &#8212; {a.hippo}</h2><div class="kpi">
<div class="kpi-item"><p class="kpi-label">Hippodrome</p><p class="kpi-value">{a.hippo}</p></div>
<div class="kpi-item"><p class="kpi-label">Discipline</p><p class="kpi-value">{a.discipline}</p></div>
<div class="kpi-item"><p class="kpi-label">Distance</p><p class="kpi-value">{a.dist}</p></div>
<div class="kpi-item"><p class="kpi-label">Partants</p><p class="kpi-value">{a.partants}</p></div>
<div class="kpi-item"><p class="kpi-label">Dotation</p><p class="kpi-value">{a.dotation}&#8364;</p></div>
</div></div>
<div class="card" style="background:#f0fdf4;border-color:#86efac;"><p style="margin:0;"><strong>Vidéo :</strong> <a href="https://youtu.be/{a.video}" target="_blank" rel="noopener">Regarder l'analyse sur YouTube &#8594;</a></p></div>
<h2>Les Partants</h2>
<table><thead><tr><th>N°</th><th>Cheval</th><th>{driver_col}</th><th>Cote</th></tr></thead><tbody>
{''.join(rows)}
</tbody></table>
<h2>Sélection du Quinté</h2><div class="card"><p><strong>Sélection de {len(sel)} chevaux :</strong></p><p>{badges}</p></div>
<h2>Top 5</h2><div class="card">{top5}</div>
{analyse}
{tickets}
<div class="card"><ul><li><strong>Gestion bankroll :</strong> max 5% par ticket</li><li><strong>Jeu responsable :</strong> ne jouez que ce que vous pouvez perdre</li></ul></div>
<p style="text-align:center;margin:2rem 0;"><a href="https://bravoquinte.github.io/bravoquinte/" class="btn">Retour à l'accueil</a></p>
<footer style="text-align:center;padding:2rem;color:var(--gray);font-size:.85rem;border-top:1px solid var(--border);margin-top:2rem;"><p><strong>Bravo Quinté</strong> &#8212; Pronostics gratuits</p><p><a href="https://bravoquinte.github.io/bravoquinte/methodologie.html">Méthodologie</a> &#183; <a href="https://bravoquinte.github.io/bravoquinte/mentions-legales.html">Mentions légales</a> &#183; <a href="https://bravoquinte.github.io/bravoquinte/track-record.html">Track Record</a> &#183; <a href="https://bravoquinte.github.io/bravoquinte/feed.xml">RSS</a></p><p>Jeu responsable : 09 74 75 13 13</p></footer>
</div></body></html>'''
    with open(os.path.join(repo, f'{a.slug}.html'), 'w', encoding='utf-8', newline='') as fh: fh.write(html)
    print(f"  article: {a.slug}.html")

def integrity_check(a):
    """Valide la cohérence des données avant publication (audit C1/C3/C4)."""
    ch = load_chevaux(a.chevaux)
    nums = sorted(int(k) for k in ch)
    sel = [int(x) for x in a.selection.split(',')]
    top = [int(x) for x in a.top5.split(',')]

    errors = []
    if a.partants != len(nums):
        errors.append(f"partants annoncés {a.partants} != {len(nums)} chevaux fournis")
    for s in sel + top:
        if not any(n == s for n in nums):
            errors.append(f"numéro {s} dans sélection/top5 absent des chevaux")
    if not any(n == a.base for n in nums):
        errors.append(f"base {a.base} absente des chevaux")
    else:
        base_name = ch.get(str(a.base), {}).get('nom', '?')
        print(f"  base: {a.base} ({base_name})")

    # contrôle doublons dans chaque liste séparément (top5 ⊂ selection est normal)
    seen_sel = set()
    for s in sel:
        if s in seen_sel:
            errors.append(f"doublon numéro {s} dans la selection")
        seen_sel.add(s)
    seen_top = set()
    for s in top:
        if s in seen_top:
            errors.append(f"doublon numéro {s} dans le top5")
        seen_top.add(s)

    if errors:
        raise SystemExit("ERREUR INTÉGRITÉ:\n  - " + "\n  - ".join(errors))
    print(f"  intégrité OK: {len(nums)} partants, sélection {len(sel)}, top5 {len(top)}")

def update_blog_posts(repo, a, date_disp):
    fp = os.path.join(repo, 'index.html')
    with open(fp, encoding='utf-8') as fh: c = fh.read()
    title = a.course.replace("'", "\u2019")
    post = f'{{title:"Pronostic Quint\u00e9 {a.hippo} {date_disp} - {title}",date:"{a.date}",slug:"{a.slug}",excerpt:"Analyse compl\u00e8te du Quint\u00e9 du jour : {title} \u00e0 {a.hippo}.",img:"{a.image}"}}'
    c = re.sub(r'(var BLOG_POSTS=\[\n?)', f'\\1{post},\n', c)
    with open(fp, 'w', encoding='utf-8', newline='') as fh: fh.write(c)
    print(f"  BLOG_POSTS: {a.slug}")

def update_resultats(repo, a):
    """Ajoute le résultat du quinté précédent dans RESULTATS[]."""
    if not a.resultat: return
    fp = os.path.join(repo, 'index.html')
    with open(fp, encoding='utf-8') as fh: c = fh.read()
    nums = a.resultat.split('-')
    ch = load_chevaux(a.chevaux_prev) if a.chevaux_prev else {}
    arr = []
    for i, n in enumerate(nums):
        n = int(n.strip())
        nom = ch.get(str(n), {}).get('nom', '?') if ch else '?'
        arr.append(f'{{n:{n},nom:"{nom}"}}')
    arrivee = ','.join(arr)
    entry = f'{{date:"{a.date_prev}",hippo:"{a.hippo_prev}",course:"{a.course_prev}",discipline:"{a.discipline_prev}",dist:"{a.dist_prev}",arrivee:[{arrivee}],rapports:"https://www.pmu.fr/turf/"}}'
    c = re.sub(r'var RESULTATS=\[\n?', f'var RESULTATS=[\n{entry},\n', c)
    with open(fp, 'w', encoding='utf-8', newline='') as fh: fh.write(c)
    print(f"  RESULTATS: {a.date_prev} {a.hippo_prev} {a.resultat}")

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--repo', default=r'C:\Users\brahi\AppData\Local\Temp\opencode\bravoquinte-export')
    for arg in ['video','date','hippo','course','discipline','dist','dotation','image','slug']:
        p.add_argument(f'--{arg}', required=True)
    p.add_argument('--partants', required=True, type=int)
    p.add_argument('--chevaux', required=True)
    p.add_argument('--selection', required=True)
    p.add_argument('--top5', required=True)
    p.add_argument('--base', required=True, type=int)
    p.add_argument('--rapports', default='https://www.pmu.fr/turf/')
    p.add_argument('--commit', action='store_true')
    # resultats du quinté precedent (optionnel)
    p.add_argument('--resultat', default=None, help='Arrivee du quinté precedent: 15-4-14-5-7')
    p.add_argument('--date-prev', default=None)
    p.add_argument('--hippo-prev', default=None)
    p.add_argument('--course-prev', default=None)
    p.add_argument('--discipline-prev', default=None)
    p.add_argument('--dist-prev', default=None)
    p.add_argument('--chevaux-prev', default=None, help='JSON chevaux du quinté precedent')
    a = p.parse_args()

    months = ['janvier','février','mars','avril','mai','juin','juillet','août','septembre','octobre','novembre','décembre']
    dt = datetime.strptime(a.date, '%Y-%m-%d')
    date_disp = f"{dt.day} {months[dt.month-1]} {dt.year}"
    a.date_disp = date_disp

    print(f"\n=== Quinté {date_disp} — {a.course} ({a.hippo}) ===")
    print(f"Base: {a.base} | Sélection: {a.selection} | Top 5: {a.top5}\n")

    integrity_check(a)
    update_index_html(a.repo, a)
    create_article(a.repo, a, date_disp)
    update_blog_posts(a.repo, a, date_disp)
    update_resultats(a.repo, a)

    # sitemap
    sp = os.path.join(a.repo, '..', 'gen-sitemap.py')
    if os.path.exists(sp):
        subprocess.run([sys.executable, sp], check=True)
        print("  sitemap: régénéré")

    if a.commit:
        subprocess.run(['git', '-C', a.repo, 'add', '-A'], check=True)
        msg = f"Daily {a.date}: {a.hippo} {a.course} - video + pronostics + post"
        subprocess.run(['git', '-C', a.repo, 'commit', '-m', msg], check=True)
        subprocess.run(['git', '-C', a.repo, 'push', 'origin', 'main'], check=True)
        print(f"  pushed: {msg}")

    print("\n=== DONE ===")

if __name__ == '__main__': main()
