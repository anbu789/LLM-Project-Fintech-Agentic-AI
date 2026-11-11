import React, { useState } from 'react';
import { Database, ChevronDown, ChevronUp, ArrowUpRight } from 'lucide-react';

export const APPROVED_COLLECTIONS = [
  {
    name: 'customers',
    primaryKey: 'customer_id',
    summary: 'Individual & corporate customer profiles',
    fields: ['kyc_status', 'risk_category', 'customer_segment', 'credit_score', 'city', 'status'],
    samplePrompt: 'Count customers in each risk category.',
  },
  {
    name: 'accounts',
    primaryKey: 'account_id',
    summary: 'Savings, current, salary, FD & RD accounts',
    fields: ['customer_id', 'branch_id', 'account_type', 'balance', 'status'],
    samplePrompt: 'Show accounts grouped by branch city.',
  },
  {
    name: 'transactions',
    primaryKey: 'transaction_id',
    summary: 'Financial transfers, card & UPI activity',
    fields: ['account_id', 'customer_id', 'merchant_id', 'amount', 'transaction_date', 'transaction_mode', 'status', 'is_flagged'],
    samplePrompt: 'How many transactions are in each transaction status?',
  },
  {
    name: 'loans',
    primaryKey: 'loan_id',
    summary: 'Home, personal, auto, education, gold & business loans',
    fields: ['customer_id', 'sanctioning_branch_id', 'loan_type', 'principal_amount', 'outstanding_amount', 'status'],
    samplePrompt: 'Count loans by loan status.',
  },
  {
    name: 'cards',
    primaryKey: 'card_id',
    summary: 'Debit & credit cards linked to accounts',
    fields: ['customer_id', 'account_id', 'card_type', 'card_network', 'credit_limit', 'status'],
    samplePrompt: 'How many cards are associated with each customer?',
  },
  {
    name: 'branches',
    primaryKey: 'branch_id',
    summary: 'Bank branch locations & facilities',
    fields: ['branch_name', 'city', 'state', 'region', 'branch_type', 'status'],
    samplePrompt: 'Show all branches located in Chennai.',
  },
  {
    name: 'employees',
    primaryKey: 'employee_id',
    summary: 'Bank staff, departments & designations',
    fields: ['branch_id', 'department', 'designation', 'employment_status'],
    samplePrompt: 'Count employees in each department.',
  },
  {
    name: 'merchants',
    primaryKey: 'merchant_id',
    summary: 'Registered payment destination merchants',
    fields: ['merchant_name', 'category', 'city', 'is_verified'],
    samplePrompt: 'Count merchants in each merchant category.',
  },
  {
    name: 'kyc_documents',
    primaryKey: 'kyc_id',
    summary: 'Masked KYC identity & verification records',
    fields: ['customer_id', 'document_type', 'verification_status', 'expiry_date'],
    samplePrompt: 'How many KYC documents are in each verification status?',
  },
  {
    name: 'fraud_alerts',
    primaryKey: 'alert_id',
    summary: 'Suspicious transaction alerts & risk scores',
    fields: ['transaction_id', 'customer_id', 'alert_type', 'risk_score', 'status', 'action_taken'],
    samplePrompt: 'Count fraud alerts by alert type and status.',
  },
  {
    name: 'support_tickets',
    primaryKey: 'ticket_id',
    summary: 'Customer service issues & resolution ratings',
    fields: ['customer_id', 'category', 'priority', 'status', 'satisfaction_rating'],
    samplePrompt: 'How many support tickets are there for each priority?',
  },
  {
    name: 'investments',
    primaryKey: 'investment_id',
    summary: 'Mutual funds, FDs, stocks, bonds & PPF portfolios',
    fields: ['customer_id', 'investment_type', 'amount_invested', 'current_value', 'risk_level', 'status'],
    samplePrompt: 'Count investments by investment type and risk level.',
  },
];

export default function SchemaGuide({ isOpen, onToggle, onSelectPrompt, disabled = false }) {
  const [selectedName, setSelectedName] = useState('customers');
  const active = APPROVED_COLLECTIONS.find((c) => c.name === selectedName) || APPROVED_COLLECTIONS[0];

  return (
    <div className="w-full border border-slate-200/90 rounded-xl bg-white shadow-card text-left overflow-hidden">
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={isOpen}
        aria-controls="approved-schema-guide-panel"
        className="w-full px-4 py-3 flex items-center justify-between gap-2 text-xs font-semibold text-slate-800 hover:bg-fintech-25 transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-fintech-500"
      >
        <span className="flex items-center space-x-2.5">
          <span className="p-1.5 rounded-md bg-fintech-50 text-fintech-700 border border-fintech-200/70">
            <Database className="w-3.5 h-3.5 shrink-0" aria-hidden="true" />
          </span>
          <span>Approved Banking Schema Guide (12 Collections)</span>
        </span>
        <span className="flex items-center space-x-1 text-fintech-700 font-medium">
          <span>{isOpen ? 'Hide' : 'Browse fields'}</span>
          {isOpen ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
        </span>
      </button>

      {isOpen && (
        <div id="approved-schema-guide-panel" className="border-t border-slate-200/90 p-4 bg-slate-50/75 space-y-3.5">
          <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-slate-700 leading-relaxed">
            <p className="max-w-[68ch]">
              Queries execute read-only against synthetic{' '}
              <code className="font-mono bg-fintech-50 text-fintech-800 px-1.5 py-0.5 rounded border border-fintech-200/70">fintech_agent_db</code>{' '}
              (19,120 INR records). Joins use domain keys rather than internal <code className="font-mono bg-fintech-50 text-fintech-800 px-1 py-0.5 rounded border border-fintech-200/70">_id</code>.
            </p>
          </div>

          <div className="flex flex-wrap gap-1.5" role="tablist" aria-label="Approved banking collections">
            {APPROVED_COLLECTIONS.map((col) => {
              const isSelected = col.name === active.name;
              return (
                <button
                  key={col.name}
                  type="button"
                  role="tab"
                  aria-selected={isSelected}
                  onClick={() => setSelectedName(col.name)}
                  className={`px-2.5 py-1.5 rounded-md text-xs font-mono transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-fintech-500 ${
                    isSelected
                      ? 'bg-fintech-700 text-white font-semibold shadow-card border border-fintech-700'
                      : 'bg-white text-slate-700 border border-slate-200 hover:border-fintech-500 hover:text-fintech-800'
                  }`}
                >
                  {col.name}
                </button>
              );
            })}
          </div>

          <div className="bg-white border border-slate-200/90 rounded-xl p-3.5 shadow-card space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-2 pb-2.5 border-b border-slate-100">
              <div className="flex flex-wrap items-baseline gap-2">
                <span className="font-mono font-semibold text-xs text-fintech-800">{active.name}</span>
                <span className="text-xs text-slate-600">{active.summary}</span>
              </div>
              <span className="text-[11px] font-mono text-fintech-800 bg-fintech-50 px-2 py-0.5 rounded-md border border-fintech-200/80 font-medium">
                PK: {active.primaryKey}
              </span>
            </div>

            <div className="flex flex-wrap gap-1.5">
              {active.fields.map((field) => (
                <code
                  key={field}
                  className="text-[11px] font-mono bg-slate-50 text-slate-800 border border-slate-200/90 px-2 py-0.5 rounded-md"
                >
                  {field}
                </code>
              ))}
            </div>

            {onSelectPrompt && (
              <div className="pt-2 border-t border-slate-100 flex items-center justify-between">
                <button
                  type="button"
                  disabled={disabled}
                  onClick={() => onSelectPrompt(active.samplePrompt)}
                  className="inline-flex items-center space-x-1.5 text-xs font-semibold text-fintech-700 hover:text-fintech-900 disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-fintech-500 rounded-md px-1 py-0.5 transition"
                >
                  <span>Try: &ldquo;{active.samplePrompt}&rdquo;</span>
                  <ArrowUpRight className="w-3.5 h-3.5" aria-hidden="true" />
                </button>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
