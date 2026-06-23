import { useState } from 'react'
import { Link } from 'react-router-dom'

import { AskPilotShell } from '../AskPilotShell'
import { UiErrorBoundary } from '../UiErrorBoundary'

import './HostPage.css'

/**
 * Demo Day Onboarding Dashboard — Authentic SharePoint UI
 * 
 * Replicates Microsoft SharePoint Online team site visual language.
 * All 6 SharePoint layout layers implemented for instant recognition:
 *   1. App Bar (far-left vertical icon strip)
 *   2. Suite Header (dark horizontal bar with search)
 *   3. Mega Navigation (blue horizontal nav bar)
 *   4. Site Header (white band with site icon + title)
 *   5. Left Site Navigation (text-based nav items)
 *   6. Content Area (web part cards on light background)
 */
export function HostPage() {
  const apiBase = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'
  const docsBase = (import.meta.env.VITE_DOCUMENTS_PUBLIC_BASE ?? '').replace(/\/$/, '')

  const [checklist, setChecklist] = useState<Record<string, boolean>>({
    techUsage: false,
    techUsePublic: false,
    emailSetup: false,
    conflictDisclosure: false,
    volunteerGuidelines: false,
    meetManager: false,
  })

  const toggleCheck = (key: string) => {
    setChecklist(prev => ({ ...prev, [key]: !prev[key] }))
  }

  const displayName = import.meta.env.VITE_PILOT_DEMO_DISPLAY_NAME ?? 'Lee Aulder'
  const userInitials = displayName
    .split(/\s+/)
    .map((part: string) => part.charAt(0))
    .join('')
    .slice(0, 2)
    .toUpperCase() || 'LA'

  return (
    <div className="askbpl-pilot-surface sp-page">
      {/* ═══════════════════════════════════════════════════════════════════════
          LAYER 1: App Bar (far-left vertical icon strip, ~48px)
          ═══════════════════════════════════════════════════════════════════════ */}
      <aside className="sp-appbar" aria-label="Microsoft 365 app launcher">
        {/* Waffle icon (signature M365 launcher) */}
        <button className="sp-appbar-icon" title="App launcher" type="button">
          <span className="sp-waffle-icon">
            <span className="sp-waffle-dot" /><span className="sp-waffle-dot" /><span className="sp-waffle-dot" />
            <span className="sp-waffle-dot" /><span className="sp-waffle-dot" /><span className="sp-waffle-dot" />
            <span className="sp-waffle-dot" /><span className="sp-waffle-dot" /><span className="sp-waffle-dot" />
          </span>
        </button>
        
        {/* Home */}
        <button className="sp-appbar-icon sp-appbar-active" title="Home" type="button">
          <svg viewBox="0 0 20 20" fill="currentColor">
            <path d="M10 2.5L2 9h2v7a1 1 0 001 1h4v-5h2v5h4a1 1 0 001-1V9h2L10 2.5z" />
          </svg>
        </button>
        
        {/* Sites */}
        <button className="sp-appbar-icon" title="Sites" type="button">
          <svg viewBox="0 0 20 20" fill="currentColor">
            <path d="M10 2a8 8 0 100 16 8 8 0 000-16zm0 2a6 6 0 11-5.917 7H10V4z" />
          </svg>
        </button>
        
        {/* News */}
        <button className="sp-appbar-icon" title="News" type="button">
          <svg viewBox="0 0 20 20" fill="currentColor">
            <path d="M2 4a2 2 0 012-2h12a2 2 0 012 2v12a2 2 0 01-2 2H4a2 2 0 01-2-2V4zm2 0v3h12V4H4zm0 5v7h5V9H4zm7 0v7h5V9h-5z" />
          </svg>
        </button>
        
        {/* Create */}
        <button className="sp-appbar-icon" title="Create" type="button">
          <svg viewBox="0 0 20 20" fill="currentColor">
            <path fillRule="evenodd" d="M10 3a1 1 0 011 1v5h5a1 1 0 110 2h-5v5a1 1 0 11-2 0v-5H4a1 1 0 110-2h5V4a1 1 0 011-1z" clipRule="evenodd" />
          </svg>
        </button>
      </aside>

      {/* ═══════════════════════════════════════════════════════════════════════
          LAYER 2: Suite Header Bar (dark horizontal bar with search)
          ═══════════════════════════════════════════════════════════════════════ */}
      <header className="sp-suite-header">
        <span className="sp-suite-brand">BPL Intranet</span>
        
        <div className="sp-suite-search">
          <div className="sp-search-box">
            <svg className="sp-search-icon" viewBox="0 0 20 20" fill="currentColor">
              <path fillRule="evenodd" d="M8 4a4 4 0 100 8 4 4 0 000-8zM2 8a6 6 0 1110.89 3.476l4.817 4.817a1 1 0 01-1.414 1.414l-4.816-4.816A6 6 0 012 8z" clipRule="evenodd" />
            </svg>
            <input 
              type="text" 
              className="sp-search-input" 
              placeholder="Search BPL Intranet"
              aria-label="Search BPL Intranet"
            />
          </div>
        </div>
        
        <div className="sp-suite-user">
          <div className="sp-user-avatar" title={displayName}>
            {userInitials}
          </div>
        </div>
      </header>

      {/* ═══════════════════════════════════════════════════════════════════════
          LAYER 3: Mega Navigation Bar (blue horizontal nav)
          ═══════════════════════════════════════════════════════════════════════ */}
      <nav className="sp-mega-nav" aria-label="Site navigation">
        <ul className="sp-mega-nav-list">
          <li className="sp-mega-nav-item">
            <a href="#" className="sp-mega-nav-link">Company Intranet</a>
          </li>
          <li className="sp-mega-nav-item">
            <a href="#" className="sp-mega-nav-link">
              Departments <span className="sp-dropdown-arrow">▾</span>
            </a>
          </li>
          <li className="sp-mega-nav-item">
            <a href="#" className="sp-mega-nav-link">
              Team Sites <span className="sp-dropdown-arrow">▾</span>
            </a>
          </li>
          <li className="sp-mega-nav-item">
            <a href="#" className="sp-mega-nav-link sp-mega-nav-active">Policies</a>
          </li>
          <li className="sp-mega-nav-item">
            <a href="#" className="sp-mega-nav-link">Employee Directory</a>
          </li>
          <li className="sp-mega-nav-item">
            <a href="#" className="sp-mega-nav-link">Projects</a>
          </li>
        </ul>
      </nav>

      {/* ═══════════════════════════════════════════════════════════════════════
          LAYER 4: Site Header (white band with site icon + title)
          ═══════════════════════════════════════════════════════════════════════ */}
      <div className="sp-site-header">
        <div className="sp-site-header-left">
          <div className="sp-site-icon">BPL</div>
          <h1 className="sp-site-title">Brooklyn Public Library — Staff Policies</h1>
        </div>
        <div className="sp-site-header-right">
          <div className="sp-site-meta">
            <span className="sp-site-meta-item">Private group</span>
            <span className="sp-site-meta-divider">·</span>
            <span className="sp-site-meta-item">★ Following</span>
            <span className="sp-site-meta-divider">·</span>
            <span className="sp-site-meta-item">👥 10 members</span>
          </div>
          <Link to="/internal/console" className="sp-build-console-link">
            Build console
          </Link>
        </div>
      </div>

      {/* ═══════════════════════════════════════════════════════════════════════
          LAYER 5 + 6: Left Site Navigation + Content Area
          ═══════════════════════════════════════════════════════════════════════ */}
      <div className="sp-site-content">
        {/* Left Site Navigation */}
        <nav className="sp-site-nav" aria-label="Site navigation">
          <ul className="sp-site-nav-list">
            <li className="sp-site-nav-item">
              <a href="#" className="sp-site-nav-link sp-site-nav-active">HR Team Home</a>
            </li>
            <li className="sp-site-nav-item">
              <a href="#" className="sp-site-nav-link">Documents</a>
            </li>
            <li className="sp-site-nav-item">
              <a href="#" className="sp-site-nav-link">Calendar</a>
            </li>
            <li className="sp-site-nav-item">
              <a href="#" className="sp-site-nav-link">Conversations</a>
            </li>
            <li className="sp-site-nav-item">
              <a href="#" className="sp-site-nav-link">Notebook</a>
            </li>
            <li className="sp-site-nav-item">
              <a href="#" className="sp-site-nav-link">Teams</a>
            </li>
            <li className="sp-site-nav-item">
              <a href="#" className="sp-site-nav-link">Planner</a>
            </li>
          </ul>
          <div className="sp-site-nav-divider" />
          <ul className="sp-site-nav-list">
            <li className="sp-site-nav-item">
              <a href="#" className="sp-site-nav-link">Edit</a>
            </li>
          </ul>
        </nav>

        {/* Content Area — Web Parts */}
        <main className="sp-content-area">
          {/* Welcome Banner — Full Width */}
          <section className="sp-webpart sp-welcome-banner" aria-labelledby="welcome-heading">
            <div className="sp-webpart-body">
              <h2 id="welcome-heading" className="sp-welcome-title">
                Welcome to Brooklyn Public Library, {displayName}!
              </h2>
              <p className="sp-welcome-text">
                Your first week onboarding checklist is below. Complete each item to get set up. 
                If you have policy questions along the way, <strong>Ask BPL</strong> is here to 
                help — look for the 📖 icon in the bottom-right corner.
              </p>
            </div>
          </section>

          <div className="sp-content-grid">
            <div className="sp-content-main">
              {/* Onboarding Checklist Web Part */}
              <section className="sp-webpart" aria-labelledby="checklist-heading">
                <div className="sp-webpart-header">
                  <h3 id="checklist-heading" className="sp-webpart-title">
                    <svg className="sp-webpart-title-icon" viewBox="0 0 20 20" fill="currentColor">
                      <path d="M6 2a2 2 0 00-2 2v12a2 2 0 002 2h8a2 2 0 002-2V4a2 2 0 00-2-2H6zm1 4a1 1 0 011-1h4a1 1 0 110 2H8a1 1 0 01-1-1zm0 3a1 1 0 011-1h4a1 1 0 110 2H8a1 1 0 01-1-1zm0 3a1 1 0 011-1h4a1 1 0 110 2H8a1 1 0 01-1-1z" />
                    </svg>
                    First Week Onboarding Checklist
                  </h3>
                  <a href="#" className="sp-webpart-action">See all</a>
                </div>
                <div className="sp-webpart-body">
                  <ul className="sp-checklist" role="list">
                    {/* Task 1: Review Technology Usage Policy */}
                    <li className="sp-checklist-item">
                      <label className="sp-checklist-label">
                        <span className="sp-checkbox">
                          <input
                            type="checkbox"
                            checked={checklist.techUsage}
                            onChange={() => toggleCheck('techUsage')}
                          />
                          <span className="sp-checkbox-box">
                            <svg className="sp-checkbox-check" viewBox="0 0 20 20" fill="currentColor">
                              <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                            </svg>
                          </span>
                        </span>
                        <div className="sp-checklist-content">
                          <span className="sp-checklist-title">Review Technology Usage Policy</span>
                          <span className="sp-checklist-desc">
                            Understand acceptable use of BPL computers, email, and network systems. 
                            Required for all staff.
                          </span>
                        </div>
                      </label>
                    </li>

                    {/* Task 2: Review Public Technology Use Policy */}
                    <li className="sp-checklist-item">
                      <label className="sp-checklist-label">
                        <span className="sp-checkbox">
                          <input
                            type="checkbox"
                            checked={checklist.techUsePublic}
                            onChange={() => toggleCheck('techUsePublic')}
                          />
                          <span className="sp-checkbox-box">
                            <svg className="sp-checkbox-check" viewBox="0 0 20 20" fill="currentColor">
                              <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                            </svg>
                          </span>
                        </span>
                        <div className="sp-checklist-content">
                          <span className="sp-checklist-title">Review Public Technology Use Policy</span>
                          <span className="sp-checklist-desc">
                            Learn the guidelines for patron computer access, internet filtering (CIPA), 
                            and Wi-Fi usage at BPL locations.
                          </span>
                        </div>
                      </label>
                    </li>

                    {/* Task 3: Set Up Email & Calendar */}
                    <li className="sp-checklist-item">
                      <label className="sp-checklist-label">
                        <span className="sp-checkbox">
                          <input
                            type="checkbox"
                            checked={checklist.emailSetup}
                            onChange={() => toggleCheck('emailSetup')}
                          />
                          <span className="sp-checkbox-box">
                            <svg className="sp-checkbox-check" viewBox="0 0 20 20" fill="currentColor">
                              <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                            </svg>
                          </span>
                        </span>
                        <div className="sp-checklist-content">
                          <span className="sp-checklist-title">Set Up Your BPL Email & Calendar</span>
                          <span className="sp-checklist-desc">
                            Contact the Office of Technology for your credentials.
                          </span>
                        </div>
                      </label>
                    </li>

                    {/* Task 4: Conflict of Interest Disclosure */}
                    <li className="sp-checklist-item">
                      <label className="sp-checklist-label">
                        <span className="sp-checkbox">
                          <input
                            type="checkbox"
                            checked={checklist.conflictDisclosure}
                            onChange={() => toggleCheck('conflictDisclosure')}
                          />
                          <span className="sp-checkbox-box">
                            <svg className="sp-checkbox-check" viewBox="0 0 20 20" fill="currentColor">
                              <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                            </svg>
                          </span>
                        </span>
                        <div className="sp-checklist-content">
                          <span className="sp-checklist-title">Complete Conflict of Interest Disclosure</span>
                          <span className="sp-checklist-desc">
                            All new employees must file a disclosure within 30 days.
                          </span>
                        </div>
                      </label>
                    </li>

                    {/* Task 5: Review Volunteer Program Guidelines */}
                    <li className="sp-checklist-item">
                      <label className="sp-checklist-label">
                        <span className="sp-checkbox">
                          <input
                            type="checkbox"
                            checked={checklist.volunteerGuidelines}
                            onChange={() => toggleCheck('volunteerGuidelines')}
                          />
                          <span className="sp-checkbox-box">
                            <svg className="sp-checkbox-check" viewBox="0 0 20 20" fill="currentColor">
                              <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                            </svg>
                          </span>
                        </span>
                        <div className="sp-checklist-content">
                          <span className="sp-checklist-title">Review Volunteer Program Guidelines</span>
                          <span className="sp-checklist-desc">
                            Understand how volunteers support staff at your branch.
                          </span>
                        </div>
                      </label>
                    </li>

                    {/* Task 6: Meet Your Branch Manager */}
                    <li className="sp-checklist-item">
                      <label className="sp-checklist-label">
                        <span className="sp-checkbox">
                          <input
                            type="checkbox"
                            checked={checklist.meetManager}
                            onChange={() => toggleCheck('meetManager')}
                          />
                          <span className="sp-checkbox-box">
                            <svg className="sp-checkbox-check" viewBox="0 0 20 20" fill="currentColor">
                              <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                            </svg>
                          </span>
                        </span>
                        <div className="sp-checklist-content">
                          <span className="sp-checklist-title">Meet Your Branch Manager</span>
                          <span className="sp-checklist-desc">
                            Schedule a 1:1 in your first week.
                          </span>
                        </div>
                      </label>
                    </li>
                  </ul>
                </div>
              </section>

              {/* Announcements Web Part */}
              <section className="sp-webpart" aria-labelledby="announcements-heading">
                <div className="sp-webpart-header">
                  <h3 id="announcements-heading" className="sp-webpart-title">
                    <svg className="sp-webpart-title-icon" viewBox="0 0 20 20" fill="currentColor">
                      <path fillRule="evenodd" d="M18 3a1 1 0 00-1.447-.894L8.763 6H5a3 3 0 000 6h.28l1.771 5.316A1 1 0 008 18h1a1 1 0 001-1v-4.382l6.553 3.276A1 1 0 0018 15V3z" clipRule="evenodd" />
                    </svg>
                    Announcements
                  </h3>
                  <a href="#" className="sp-webpart-action">See all</a>
                </div>
                <div className="sp-webpart-body">
                  <ul className="sp-announcements" role="list">
                    <li className="sp-announcement-item">
                      <span className="sp-announcement-date">Jun 20</span>
                      <span className="sp-announcement-text">Summer Reading Program kicks off June 20</span>
                    </li>
                    <li className="sp-announcement-item">
                      <span className="sp-announcement-date">Jun 14</span>
                      <span className="sp-announcement-text">
                        Office of Technology: System maintenance June 14, 10PM–2AM
                      </span>
                    </li>
                    <li className="sp-announcement-item">
                      <span className="sp-announcement-date">Weekly</span>
                      <span className="sp-announcement-text">
                        New staff orientation sessions every Monday at 10AM
                      </span>
                    </li>
                  </ul>
                </div>
              </section>
            </div>

            <div className="sp-content-sidebar">
              {/* Quick Links Web Part */}
              <section className="sp-webpart" aria-labelledby="quicklinks-heading">
                <div className="sp-webpart-header">
                  <h3 id="quicklinks-heading" className="sp-webpart-title">
                    <svg className="sp-webpart-title-icon" viewBox="0 0 20 20" fill="currentColor">
                      <path fillRule="evenodd" d="M12.586 4.586a2 2 0 112.828 2.828l-3 3a2 2 0 01-2.828 0 1 1 0 00-1.414 1.414 4 4 0 005.656 0l3-3a4 4 0 00-5.656-5.656l-1.5 1.5a1 1 0 101.414 1.414l1.5-1.5zm-5 5a2 2 0 012.828 0 1 1 0 101.414-1.414 4 4 0 00-5.656 0l-3 3a4 4 0 105.656 5.656l1.5-1.5a1 1 0 10-1.414-1.414l-1.5 1.5a2 2 0 11-2.828-2.828l3-3z" clipRule="evenodd" />
                    </svg>
                    Quick Links
                  </h3>
                </div>
                <div className="sp-webpart-body">
                  <div className="sp-quicklinks">
                    <a href="#" className="sp-quicklink-item">
                      <span className="sp-quicklink-icon">
                        <svg viewBox="0 0 20 20" fill="currentColor">
                          <path d="M9 2a1 1 0 000 2h2a1 1 0 100-2H9z" />
                          <path fillRule="evenodd" d="M4 5a2 2 0 012-2 3 3 0 003 3h2a3 3 0 003-3 2 2 0 012 2v11a2 2 0 01-2 2H6a2 2 0 01-2-2V5zm3 4a1 1 0 000 2h.01a1 1 0 100-2H7zm3 0a1 1 0 000 2h3a1 1 0 100-2h-3zm-3 4a1 1 0 100 2h.01a1 1 0 100-2H7zm3 0a1 1 0 100 2h3a1 1 0 100-2h-3z" clipRule="evenodd" />
                        </svg>
                      </span>
                      <span className="sp-quicklink-label">Policy Library</span>
                    </a>
                    <a href="#" className="sp-quicklink-item">
                      <span className="sp-quicklink-icon">
                        <svg viewBox="0 0 20 20" fill="currentColor">
                          <path fillRule="evenodd" d="M3 5a2 2 0 012-2h10a2 2 0 012 2v8a2 2 0 01-2 2h-2.22l.123.489.804.804A1 1 0 0113 18H7a1 1 0 01-.707-1.707l.804-.804L7.22 15H5a2 2 0 01-2-2V5zm5.771 7H5V5h10v7H8.771z" clipRule="evenodd" />
                        </svg>
                      </span>
                      <span className="sp-quicklink-label">IT Help Desk</span>
                    </a>
                    <a href="#" className="sp-quicklink-item">
                      <span className="sp-quicklink-icon">
                        <svg viewBox="0 0 20 20" fill="currentColor">
                          <path fillRule="evenodd" d="M6 2a1 1 0 00-1 1v1H4a2 2 0 00-2 2v10a2 2 0 002 2h12a2 2 0 002-2V6a2 2 0 00-2-2h-1V3a1 1 0 10-2 0v1H7V3a1 1 0 00-1-1zm0 5a1 1 0 000 2h8a1 1 0 100-2H6z" clipRule="evenodd" />
                        </svg>
                      </span>
                      <span className="sp-quicklink-label">Staff Calendar</span>
                    </a>
                    <a href="#" className="sp-quicklink-item">
                      <span className="sp-quicklink-icon">
                        <svg viewBox="0 0 20 20" fill="currentColor">
                          <path d="M2 3a1 1 0 011-1h2.153a1 1 0 01.986.836l.74 4.435a1 1 0 01-.54 1.06l-1.548.773a11.037 11.037 0 006.105 6.105l.774-1.548a1 1 0 011.059-.54l4.435.74a1 1 0 01.836.986V17a1 1 0 01-1 1h-2C7.82 18 2 12.18 2 5V3z" />
                        </svg>
                      </span>
                      <span className="sp-quicklink-label">HR Contact</span>
                    </a>
                  </div>
                </div>
              </section>

              {/* Ask BPL Promo Card */}
              <section className="sp-webpart sp-askbpl-promo" aria-labelledby="askbpl-heading">
                <div className="sp-webpart-header">
                  <h3 id="askbpl-heading" className="sp-webpart-title">
                    <svg className="sp-webpart-title-icon" viewBox="0 0 20 20" fill="currentColor">
                      <path d="M9 4.804A7.968 7.968 0 005.5 4c-1.255 0-2.443.29-3.5.804v10A7.969 7.969 0 015.5 14c1.669 0 3.218.51 4.5 1.385A7.962 7.962 0 0114.5 14c1.255 0 2.443.29 3.5.804v-10A7.968 7.968 0 0014.5 4c-1.255 0-2.443.29-3.5.804V12a1 1 0 11-2 0V4.804z" />
                    </svg>
                    Have a policy question?
                  </h3>
                </div>
                <div className="sp-webpart-body">
                  <p className="sp-askbpl-promo-text">
                    <strong>Ask BPL</strong> can help. Click the 📖 icon in the bottom-right 
                    to get started.
                  </p>
                </div>
              </section>
            </div>
          </div>
        </main>
      </div>

      {/* Floating Ask BPL Widget (rendered by parent, preserved here) */}
      <UiErrorBoundary
        label="AskPilotShell"
        fallback={
          <section className="sp-webpart" role="alert" style={{ margin: '1rem' }}>
            <h3>Chat shell crashed</h3>
            <p>
              Open DevTools → Console for the stack trace. The pilot build
              runs in wireframe-modal mode by default; set{' '}
              <code>VITE_ENABLE_AVATAR_SHELL=true</code> only if you want the
              draggable avatar variant back.
            </p>
          </section>
        }
      >
        <AskPilotShell apiBase={apiBase} docsBase={docsBase} />
      </UiErrorBoundary>
    </div>
  )
}
