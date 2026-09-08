"""Check line coverage separately for every production Python package."""
import argparse
import json
from pathlib import Path

PACKAGES = ('engine', 'shell', 'agent')
ROOT = Path(__file__).resolve().parents[1]


def assess(report, minimum=80):
    files = report.get('files')
    if not isinstance(files, dict) or not files:
        raise ValueError('coverage report has no files')
    rows = []
    for package in PACKAGES:
        summaries = [file['summary'] for name, file in files.items()
                     if name.replace('\\', '/').startswith(package + '/src/')]
        if not summaries:
            raise ValueError('coverage report has no production files for ' + package)
        for summary in summaries:
            covered, total = summary['covered_lines'], summary['num_statements']
            if not (isinstance(covered, int) and isinstance(total, int)
                    and 0 <= covered <= total):
                raise ValueError('invalid line counts for ' + package)
        covered = sum(s['covered_lines'] for s in summaries)
        total = sum(s['num_statements'] for s in summaries)
        if not total:
            raise ValueError('coverage report has no statements for ' + package)
        rows.append(dict(package=package, covered=covered, total=total,
                         percent=100 * covered / total,
                         passed=100 * covered >= minimum * total))
    return rows


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report', type=Path)
    args = parser.parse_args(argv)
    try:
        payload = json.loads(args.report.read_text())
        expected = {path.relative_to(ROOT).as_posix() for package in PACKAGES
                    for path in (ROOT / package / 'src').rglob('*.py')}
        missing = expected - set(payload.get('files', {}))
        if missing:
            raise ValueError('production files missing from coverage: ' + ', '.join(sorted(missing)))
        rows = assess(payload)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print('Coverage gate failed: ' + str(exc))
        return 1
    for row in rows:
        print('{package}: {covered}/{total} lines, {percent:.2f}% ({verdict}, minimum 80%)'.format(
            **row, verdict='PASS' if row['passed'] else 'FAIL'))
    return 0 if all(row['passed'] for row in rows) else 1


if __name__ == '__main__':
    raise SystemExit(main())
