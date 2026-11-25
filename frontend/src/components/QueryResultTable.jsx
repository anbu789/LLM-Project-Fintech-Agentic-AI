import React, { useMemo, useState } from 'react';
import { Table2, Code2, Hash, Layers, CheckCircle2, FileText, ChevronRight, Download } from 'lucide-react';

/**
 * Triggers a browser file download safely.
 */
export function triggerFileDownload(content, filename, mimeType) {
  if (typeof window === 'undefined' || typeof document === 'undefined') return;
  const blob = new Blob([content], { type: mimeType });
  if (typeof URL.createObjectURL === 'function') {
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    if (typeof URL.revokeObjectURL === 'function') {
      URL.revokeObjectURL(url);
    }
  }
}

/**
 * Exports data rows to CSV string with standard quoting and escaping.
 */
export function convertRowsToCSV(columns, rows) {
  const escapeCsv = (val) => {
    if (val === null || val === undefined) return '';
    const str = typeof val === 'object' ? JSON.stringify(val) : String(val);
    if (str.includes(',') || str.includes('"') || str.includes('\n') || str.includes('\r')) {
      return `"${str.replace(/"/g, '""')}"`;
    }
    return str;
  };

  const headerLine = columns.map(escapeCsv).join(',');
  const dataLines = rows.map((row) =>
    columns.map((col) => escapeCsv(row ? row[col] : '')).join(',')
  );

  return [headerLine, ...dataLines].join('\r\n');
}

/**
 * Exports data rows to a formatted GitHub-Flavored Markdown table.
 */
export function convertRowsToMarkdown(columns, rows, summaryTitle = null) {
  const escapeMd = (val) => {
    if (val === null || val === undefined) return '—';
    const str = formatCellValue(val);
    return str.replace(/\|/g, '\\|').replace(/\r?\n/g, ' ');
  };

  const header = `| # | ${columns.join(' | ')} |`;
  const separator = `|:---:|${columns.map(() => ':---').join('|')}|`;
  const body = rows.map((row, idx) => {
    const cells = columns.map((col) => escapeMd(row ? row[col] : ''));
    return `| ${idx + 1} | ${cells.join(' | ')} |`;
  });

  const lines = [
    '# FinTech Agent — Query Results',
    '',
    summaryTitle ? `**Summary:** ${summaryTitle}  ` : '',
    `**Exported:** ${new Date().toISOString()}  `,
    `**Total Rows:** ${rows.length}`,
    '',
    header,
    separator,
    ...body,
    '',
  ].filter((l) => l !== '');

  return lines.join('\n');
}

/**
 * Formats any cell value into a clean, human-readable string.
 * Recursively formats nested objects, arrays, and MongoDB BSON types.
 */
export function formatCellValue(value) {
  if (value === null || value === undefined) {
    return '—';
  }

  // Boolean
  if (typeof value === 'boolean') {
    return value ? 'True' : 'False';
  }

  // Number
  if (typeof value === 'number') {
    if (Number.isInteger(value)) {
      return value.toLocaleString();
    }
    return value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  // MongoDB Extended JSON object types (BSON representation)
  if (typeof value === 'object') {
    if (value.$oid) return String(value.$oid);
    if (value.$date) {
      const d = new Date(value.$date);
      return Number.isNaN(d.getTime()) ? String(value.$date) : d.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });
    }
    if (value.$numberDecimal) {
      const num = parseFloat(value.$numberDecimal);
      return Number.isNaN(num) ? String(value.$numberDecimal) : num.toLocaleString();
    }
    if (value.$numberLong || value.$numberInt) {
      return String(value.$numberLong || value.$numberInt);
    }

    // Arrays
    if (Array.isArray(value)) {
      if (value.length === 0) return '—';
      const allPrimitives = value.every((v) => v === null || typeof v !== 'object');
      if (allPrimitives) {
        return value.map((v) => (v === null ? '—' : String(v))).join(', ');
      }
      return value
        .map((item) => {
          if (item && typeof item === 'object') {
            return Object.entries(item)
              .map(([k, v]) => `${k}: ${typeof v === 'object' ? JSON.stringify(v) : v}`)
              .join(', ');
          }
          return String(item);
        })
        .join('; ');
    }

    // Nested Objects
    const entries = Object.entries(value);
    if (entries.length === 0) return '—';
    return entries
      .map(([k, v]) => {
        if (v === null || v === undefined) return `${k}: —`;
        if (typeof v === 'object') {
          if (Array.isArray(v)) return `${k}: [${v.join(', ')}]`;
          return `${k}: {${Object.entries(v).map(([subK, subV]) => `${subK}: ${subV}`).join(', ')}}`;
        }
        return `${k}: ${v}`;
      })
      .join(', ');
  }

  // String
  if (typeof value === 'string') {
    // Check if ISO 8601 date string
    if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}/.test(value)) {
      const d = new Date(value);
      if (!Number.isNaN(d.getTime())) {
        return d.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });
      }
    }
    return value;
  }

  return String(value);
}

/**
 * Derives unique, ordered column names from an array of document objects.
 * Puts primary identifiers (_id, *id, *name) at the front if present.
 */
export function deriveColumns(rows) {
  if (!Array.isArray(rows) || rows.length === 0) return [];
  const colSet = new Set();

  for (const row of rows) {
    if (row && typeof row === 'object' && !Array.isArray(row)) {
      for (const key of Object.keys(row)) {
        colSet.add(key);
      }
    }
  }

  const cols = Array.from(colSet);

  // Sort priority: _id first, then common IDs, then other keys
  return cols.sort((a, b) => {
    if (a === '_id') return -1;
    if (b === '_id') return 1;
    const aIsId = a.endsWith('_id') || a.endsWith('Id');
    const bIsId = b.endsWith('_id') || b.endsWith('Id');
    if (aIsId && !bIsId) return -1;
    if (!aIsId && bIsId) return 1;
    return 0;
  });
}

/**
 * Formats a key name into readable title case: e.g. "active_home_loan_count" -> "Active Home Loan Count"
 */
function humanizeKey(key) {
  if (!key) return '';
  return key
    .replace(/^_+/, '')
    .split('_')
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ');
}

/**
 * Generates an accurate, natural-language summary of the query result set
 * without inventing any extra statistics.
 */
export function generateResultSummary(rows, totalCount, targetCollection) {
  if (!Array.isArray(rows) || rows.length === 0) {
    return {
      type: 'empty',
      title: 'No records found',
      description: 'The query executed successfully, but matched 0 documents in the database.',
      highlight: null,
    };
  }

  const effectiveTotal = typeof totalCount === 'number' ? totalCount : rows.length;

  // 1. Single-row count query: e.g. [{ "active_home_loan_count": 89 }] or [{ "count": 1500 }]
  if (rows.length === 1) {
    const single = rows[0];
    if (single && typeof single === 'object') {
      const keys = Object.keys(single);
      const countKey = keys.find((k) =>
        /count|total|sum|amount|avg|min|max/i.test(k) || (keys.length === 1 && typeof single[k] === 'number')
      );

      if (countKey && typeof single[countKey] === 'number') {
        const readableLabel = humanizeKey(countKey);
        const formattedVal = single[countKey].toLocaleString();
        return {
          type: 'count',
          title: `${readableLabel}: ${formattedVal}`,
          description: `Query completed with 1 aggregation result: ${readableLabel} is ${formattedVal}.`,
          highlight: {
            label: readableLabel,
            value: formattedVal,
          },
        };
      }
    }
  }

  // 2. Group aggregation query: e.g. [{ _id: 'verified', count: 640 }, { _id: 'pending', count: 120 }]
  const isGroupAggregation =
    rows.length > 1 &&
    rows.every(
      (r) =>
        r &&
        typeof r === 'object' &&
        ('_id' in r || 'group' in r || 'category' in r) &&
        ('count' in r || 'total' in r || 'sum' in r || 'amount' in r)
    );

  if (isGroupAggregation) {
    const groupField = '_id' in rows[0] ? '_id' : 'category' in rows[0] ? 'category' : 'group';
    const metricField = 'count' in rows[0] ? 'count' : 'total' in rows[0] ? 'total' : 'amount';

    const groupSnippets = rows.slice(0, 5).map((r) => {
      const groupName = r[groupField] === null ? 'None' : String(r[groupField]);
      const metricVal = typeof r[metricField] === 'number' ? r[metricField].toLocaleString() : String(r[metricField]);
      return `${groupName} (${metricVal})`;
    });

    const hasMore = rows.length > 5;
    const groupListText = groupSnippets.join(', ') + (hasMore ? `, and ${rows.length - 5} more` : '');

    return {
      type: 'aggregation',
      title: `Grouped into ${rows.length} categories`,
      description: `Returned ${rows.length} aggregate categories: ${groupListText}.`,
      highlight: null,
    };
  }

  // 3. Multi-document listing/filter query: e.g. 61 defaulted loans, 27 dining merchants
  const colName = targetCollection ? `from \`${targetCollection}\`` : 'from database';
  const previewNote =
    effectiveTotal > rows.length
      ? `Displaying ${rows.length} preview records out of ${effectiveTotal.toLocaleString()} total returned records.`
      : `Displaying all ${rows.length} returned records.`;

  return {
    type: 'list',
    title: `Retrieved ${effectiveTotal.toLocaleString()} ${effectiveTotal === 1 ? 'record' : 'records'} ${colName}`,
    description: `Query executed successfully against the database. ${previewNote}`,
    highlight: null,
  };
}

export default function QueryResultTable({
  rows = [],
  totalCount = null,
  executionTimeMs = null,
  targetCollection = null,
  onExport = null,
}) {
  const [showRawJson, setShowRawJson] = useState(false);

  const columns = useMemo(() => deriveColumns(rows), [rows]);
  const summary = useMemo(
    () => generateResultSummary(rows, totalCount, targetCollection),
    [rows, totalCount, targetCollection]
  );

  const handleExport = (format) => {
    const timestamp = new Date().toISOString().slice(0, 10);
    const sanitizedCol = (targetCollection || 'query_results').toLowerCase().replace(/[^a-z0-9_-]/g, '_');

    let content = '';
    let filename = '';
    let mimeType = '';

    if (format === 'csv') {
      content = convertRowsToCSV(columns, rows);
      filename = `${sanitizedCol}_${timestamp}.csv`;
      mimeType = 'text/csv;charset=utf-8;';
    } else if (format === 'md') {
      content = convertRowsToMarkdown(columns, rows, summary.title);
      filename = `${sanitizedCol}_${timestamp}.md`;
      mimeType = 'text/markdown;charset=utf-8;';
    } else if (format === 'json') {
      content = JSON.stringify(rows, null, 2);
      filename = `${sanitizedCol}_${timestamp}.json`;
      mimeType = 'application/json;charset=utf-8;';
    }

    if (typeof onExport === 'function') {
      onExport({ format, content, filename, mimeType });
    }
    triggerFileDownload(content, filename, mimeType);
  };

  if (!Array.isArray(rows) || rows.length === 0) {
    return (
      <div className="my-3 p-3.5 bg-slate-50 border border-slate-200/90 rounded-xl text-slate-700 text-xs flex items-center space-x-2">
        <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" aria-hidden="true" />
        <span>No matching documents returned.</span>
      </div>
    );
  }

  return (
    <div className="my-3 space-y-2.5 max-w-full">
      {/* 1. Natural Language Summary Card */}
      <div className="p-3.5 bg-slate-50/90 border border-slate-200/90 rounded-xl text-slate-800 shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-200/70 pb-2">
          <div className="flex items-center space-x-2">
            {summary.type === 'count' ? (
              <div className="w-6 h-6 rounded-md bg-fintech-100 text-fintech-700 flex items-center justify-center shrink-0">
                <Hash className="w-3.5 h-3.5" aria-hidden="true" />
              </div>
            ) : summary.type === 'aggregation' ? (
              <div className="w-6 h-6 rounded-md bg-amber-100 text-amber-700 flex items-center justify-center shrink-0">
                <Layers className="w-3.5 h-3.5" aria-hidden="true" />
              </div>
            ) : (
              <div className="w-6 h-6 rounded-md bg-emerald-100 text-emerald-700 flex items-center justify-center shrink-0">
                <Table2 className="w-3.5 h-3.5" aria-hidden="true" />
              </div>
            )}
            <span className="text-xs font-semibold text-slate-900 tracking-tight">
              {summary.title}
            </span>
          </div>

          <div className="flex flex-wrap items-center gap-1.5 text-[11px]">
            {executionTimeMs != null && (
              <span className="text-slate-500 font-mono mr-1">
                {executionTimeMs} ms
              </span>
            )}

            {/* Download Export Toolbar */}
            <div className="inline-flex items-center rounded-md border border-slate-200 bg-white p-0.5 shadow-xs">
              <span className="px-1.5 py-0.5 text-slate-400 font-medium inline-flex items-center gap-1">
                <Download className="w-3 h-3 text-slate-500" aria-hidden="true" />
                <span className="hidden sm:inline">Export:</span>
              </span>
              <button
                type="button"
                onClick={() => handleExport('csv')}
                title="Download results as CSV"
                aria-label="Download results as CSV"
                className="px-2 py-0.5 font-semibold text-slate-700 hover:text-fintech-700 hover:bg-slate-100 rounded transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-fintech-500"
              >
                CSV
              </button>
              <button
                type="button"
                onClick={() => handleExport('md')}
                title="Download results as Markdown"
                aria-label="Download results as Markdown"
                className="px-2 py-0.5 font-semibold text-slate-700 hover:text-fintech-700 hover:bg-slate-100 rounded transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-fintech-500"
              >
                MD
              </button>
              <button
                type="button"
                onClick={() => handleExport('json')}
                title="Download results as JSON"
                aria-label="Download results as JSON"
                className="px-2 py-0.5 font-semibold text-slate-700 hover:text-fintech-700 hover:bg-slate-100 rounded transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-fintech-500"
              >
                JSON
              </button>
            </div>

            {/* View Raw JSON / Table Toggle */}
            <button
              type="button"
              onClick={() => setShowRawJson((prev) => !prev)}
              className="inline-flex items-center space-x-1 text-fintech-700 hover:text-fintech-900 bg-white border border-slate-200 hover:border-fintech-300 px-2 py-0.5 rounded-md font-semibold transition shadow-xs focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-fintech-500"
            >
              {showRawJson ? (
                <>
                  <Table2 className="w-3 h-3" aria-hidden="true" />
                  <span>View Table</span>
                </>
              ) : (
                <>
                  <Code2 className="w-3 h-3" aria-hidden="true" />
                  <span>View Raw JSON</span>
                </>
              )}
            </button>
          </div>
        </div>

        {/* Concise Natural Language Description */}
        <p className="text-xs text-slate-700 leading-relaxed mt-2">
          {summary.description}
        </p>

        {/* Count query callout highlight badge */}
        {summary.highlight && (
          <div className="mt-2.5 inline-flex items-center space-x-2 bg-white border border-fintech-200 px-3 py-1.5 rounded-lg shadow-xs">
            <span className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider">
              {summary.highlight.label}:
            </span>
            <span className="text-sm font-bold text-fintech-900 font-mono tabular-nums">
              {summary.highlight.value}
            </span>
          </div>
        )}
      </div>

      {/* 2. Results Content: Clean Table View or Raw JSON Toggle */}
      {showRawJson ? (
        <div className="rounded-xl border border-fintech-800/70 bg-fintech-950 p-3.5 shadow-card overflow-hidden">
          <div className="flex items-center justify-between text-[11px] font-mono text-slate-400 mb-2 border-b border-fintech-800 pb-1.5">
            <span>Raw MongoDB Documents ({rows.length} items)</span>
          </div>
          <pre className="text-xs font-mono text-emerald-300 max-h-72 overflow-auto leading-relaxed">
            {JSON.stringify(rows, null, 2)}
          </pre>
        </div>
      ) : (
        <div className="rounded-xl border border-slate-200/90 bg-white shadow-card overflow-hidden">
          {/* Scrollable table container supporting horizontal scrolling for wide schemas */}
          <div className="max-w-full overflow-x-auto max-h-80 overflow-y-auto">
            <table className="min-w-full divide-y divide-slate-200 text-xs tabular-nums text-left border-collapse">
              <thead className="bg-slate-50/95 text-slate-800 font-semibold sticky top-0 z-10 border-b border-slate-200 shadow-xs">
                <tr>
                  <th scope="col" className="px-3 py-2 text-center text-slate-400 font-mono text-[10px] w-10 shrink-0">
                    #
                  </th>
                  {columns.map((col) => (
                    <th
                      key={col}
                      scope="col"
                      className="px-3.5 py-2.5 font-semibold text-slate-800 whitespace-nowrap"
                    >
                      {col}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 bg-white">
                {rows.map((row, rowIdx) => (
                  <tr
                    key={rowIdx}
                    className="hover:bg-slate-50/80 transition-colors duration-100"
                  >
                    <td className="px-3 py-2 text-center text-slate-400 font-mono text-[11px] select-none bg-slate-50/40">
                      {rowIdx + 1}
                    </td>
                    {columns.map((col) => {
                      const rawVal = row ? row[col] : undefined;
                      const formatted = formatCellValue(rawVal);
                      const isNull = rawVal === null || rawVal === undefined;

                      return (
                        <td
                          key={col}
                          className={`px-3.5 py-2 align-top text-xs ${
                            isNull ? 'text-slate-400 italic' : 'text-slate-800'
                          } whitespace-nowrap max-w-xs truncate`}
                          title={typeof rawVal === 'object' ? JSON.stringify(rawVal) : String(rawVal ?? '')}
                        >
                          {formatted}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Table Footer info */}
          <div className="px-3.5 py-2 bg-slate-50/70 border-t border-slate-200/80 text-[11px] text-slate-500 flex flex-wrap items-center justify-between gap-2">
            <span>
              Showing {rows.length} {rows.length === 1 ? 'row' : 'rows'} × {columns.length} columns
            </span>
            {totalCount != null && totalCount > rows.length && (
              <span className="text-amber-700 font-medium">
                Results preview capped at {rows.length} of {totalCount.toLocaleString()} total documents
              </span>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
