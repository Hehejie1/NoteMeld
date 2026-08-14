---
name: Structured Intelligence
colors:
  surface: '#f8f9fb'
  surface-dim: '#d9dadc'
  surface-bright: '#f8f9fb'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#f3f4f6'
  surface-container: '#edeef0'
  surface-container-high: '#e7e8ea'
  surface-container-highest: '#e1e2e4'
  on-surface: '#191c1e'
  on-surface-variant: '#464556'
  inverse-surface: '#2e3132'
  inverse-on-surface: '#f0f1f3'
  outline: '#777588'
  outline-variant: '#c7c4d9'
  surface-tint: '#493df4'
  primary: '#3118e0'
  on-primary: '#ffffff'
  primary-container: '#4c40f6'
  on-primary-container: '#dbd8ff'
  inverse-primary: '#c3c0ff'
  secondary: '#5e5e60'
  on-secondary: '#ffffff'
  secondary-container: '#e0dfe2'
  on-secondary-container: '#626265'
  tertiary: '#46494e'
  on-tertiary: '#ffffff'
  tertiary-container: '#5e6166'
  on-tertiary-container: '#dadce2'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#e2dfff'
  primary-fixed-dim: '#c3c0ff'
  on-primary-fixed: '#0e006a'
  on-primary-fixed-variant: '#2e11de'
  secondary-fixed: '#e3e2e4'
  secondary-fixed-dim: '#c7c6c8'
  on-secondary-fixed: '#1b1c1e'
  on-secondary-fixed-variant: '#464749'
  tertiary-fixed: '#e0e2e8'
  tertiary-fixed-dim: '#c4c6cc'
  on-tertiary-fixed: '#181c20'
  on-tertiary-fixed-variant: '#44474b'
  background: '#f8f9fb'
  on-background: '#191c1e'
  surface-variant: '#e1e2e4'
  editor-bg: '#FFFFFF'
  sidebar-bg: '#F8F9FA'
  border-subtle: '#E5E6EB'
  status-success: '#00B42A'
  status-info: '#0067ED'
typography:
  headline-xl:
    fontFamily: Hanken Grotesk
    fontSize: 40px
    fontWeight: '700'
    lineHeight: 48px
    letterSpacing: -0.02em
  headline-lg:
    fontFamily: Hanken Grotesk
    fontSize: 32px
    fontWeight: '600'
    lineHeight: 40px
    letterSpacing: -0.01em
  headline-md:
    fontFamily: Hanken Grotesk
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
  body-lg:
    fontFamily: Noto Sans SC
    fontSize: 18px
    fontWeight: '400'
    lineHeight: 28px
  body-md:
    fontFamily: Noto Sans SC
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 24px
  body-sm:
    fontFamily: Noto Sans SC
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
  label-caps:
    fontFamily: JetBrains Mono
    fontSize: 12px
    fontWeight: '500'
    lineHeight: 16px
    letterSpacing: 0.05em
  code-inline:
    fontFamily: JetBrains Mono
    fontSize: 13px
    fontWeight: '400'
    lineHeight: 20px
rounded:
  sm: 0.125rem
  DEFAULT: 0.25rem
  md: 0.375rem
  lg: 0.5rem
  xl: 0.75rem
  full: 9999px
spacing:
  unit: 4px
  sidebar-width: 260px
  container-max: 1200px
  gutter: 24px
  margin-mobile: 16px
  margin-desktop: 32px
url: 'https://stitch.withgoogle.com/projects/881804300763042605'
---

## Brand & Style

The design system is engineered for **NoteMeld**, a knowledge management tool that bridges the gap between multimedia consumption and structured documentation. The brand personality is **Precise, Academic, and Efficient**. It targets researchers, students, and power users who need to synthesize vast amounts of information into actionable wikis.

The visual style is **Corporate Modern with a Minimalist focus**. It prioritizes extreme clarity and information density without feeling cluttered. Drawing inspiration from high-end development environments and modern SaaS platforms, the system utilizes high-quality typography, a restrained color palette, and systematic spacing to create a sense of professional reliability and intellectual calm.

## Colors

The palette is anchored in a high-contrast relationship between **Deep Indigo (#4C40F6)** and **Stark White (#FFFFFF)**.

- **Primary:** The Indigo is used sparingly for primary actions, focus states, and key navigational highlights, ensuring the user's attention is directed toward conversion or creation.
- **Secondary/Neutral:** A sophisticated range of grays manages the interface's skeleton. `#F2F3F5` serves as the canvas background, while `#1A1B1D` provides maximum legibility for body text.
- **Surface Strategy:** Use white for the primary workspace (wiki editor) to mimic physical paper, and subtle grays for utility areas like sidebars and metadata panels to create a clear "work-vs-tool" mental model.

## Typography

This design system uses a multi-layered typographic approach to balance modern aesthetics with multi-language support (Chinese and Latin scripts).

- **Headlines:** Uses **Hanken Grotesk** for its sharp, contemporary geometric feel. It creates a strong hierarchy and feels "engineered."
- **Body:** **Noto Sans SC** is the workhorse, selected for its exceptional readability in both Simplified Chinese and English, maintaining a consistent optical weight across languages.
- **Labels & System Info:** **JetBrains Mono** is used for metadata, timestamps, and the chat interface's technical details to evoke the "knowledge-wiki" and "data-processing" nature of the tool.
- **Readability:** Body text should maintain a 65-75 character line length for optimal reading comfort in long-form notes.

## Layout & Spacing

The design system utilizes a **fixed-fluid hybrid grid** model. 

1. **Sidebar Navigation:** A fixed-width left sidebar (260px) houses the workspace hierarchy. It uses a condensed spacing rhythm (8px between items) to maximize visibility of complex folder structures.
2. **Main Canvas:** A fluid central area that caps at 1200px for document readability. 
3. **Chat/AI Overlay:** A docked or slide-out panel on the right, mirroring the sidebar’s structural logic.
4. **Breakpoints:**
   - **Desktop (1280px+):** Full 3-column layout (Sidebar + Editor + AI Chat).
   - **Tablet (768px - 1279px):** Sidebar becomes a collapsible drawer; Editor and AI Chat share the screen.
   - **Mobile (<768px):** Single column focused on reading/chatting, with navigation hidden behind a bottom bar or "hamburger" menu.

## Elevation & Depth

This design system avoids heavy drop shadows, instead using **Tonal Layers** and **Low-Contrast Outlines** to define hierarchy.

- **Level 0 (Background):** `#F2F3F5` - The base surface.
- **Level 1 (Cards/Editor):** White background with a 1px solid border (`#E5E6EB`). No shadow.
- **Level 2 (Hover/Active):** A very soft, diffused shadow (`0 4px 12px rgba(0,0,0,0.05)`) and a subtle border color shift to the primary indigo.
- **Level 3 (Modals/Popovers):** A crisp 1px border with a medium-diffused shadow to separate the element from the workspace.

This approach creates a "flat-yet-layered" look that feels more like an organized physical desk than a traditional 3D software interface.

## Shapes

The shape language is **Soft and Precise**. 

- **Base Radius:** 4px (0.25rem) for functional elements like buttons, inputs, and chips. This sharpness reinforces the "professional tool" aesthetic.
- **Large Radius:** 8px (0.5rem) for main content cards and the editor surface, providing a slight visual approachable softness.
- **Interactive Elements:** Use a subtle 1px border on all interactive components to maintain high definition against the neutral backgrounds.

## Components

- **Buttons:** Primary buttons use a solid `#4C40F6` background with white text. Secondary buttons use a white background with a `#E5E6EB` border. Ghost buttons are reserved for low-priority sidebar actions.
- **Wiki Cards:** Inspired by "Structured Intelligence," cards feature a top-heavy layout with bold titles, followed by a metadata row (using `label-caps`) and a 3-line summary. Hovering a card should trigger a 1px primary border.
- **Chat Input:** A modern, multi-line input area with a "pill-shaped" container. It should include integrated icons for "Attach Video" or "Link URL," styled with secondary gray icons that turn primary indigo on focus.
- **Sidebar Items:** High-density list items with a 32px height. Active states are indicated by a subtle left-aligned 3px vertical "pill" of primary color, rather than a full background highlight.
- **Chips/Tags:** Small, rectangular badges with 2px radius and light tinted backgrounds (e.g., 10% opacity of primary color) to categorize note types (Video, Web, Manual).