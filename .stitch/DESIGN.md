# Design System: JobAgent

## 1. Visual Style
- **Color Palette**: 
  - Primary: `#4f46e5` (Indigo)
  - Success: `#10b981` (Emerald)
  - Warning: `#f59e0b` (Amber)
  - Danger: `#ef4444` (Red)
  - Background: White (Light) / Dark Gray (Dark)
- **Typography**: Inter (Sans-serif), tracking-tight for headings.
- **Roundness**: Rounded-lg (8px).
- **Aesthetics**: Clean, SaaS-modern, subtle glassmorphism on cards.

## 2. Components
- **Cards**: Bordered with light shadows.
- **Badges**: pill-shaped, uppercase tracking-wider.
- **Buttons**: Strong solid colors for primary actions, outlined for secondary.

## 3. Layout Patterns
- **Sidebar Navigation**: Dashboard, Automation, Jobs, Analytics, Knowledge Graph.
- **Header**: User details, Notifications.
- **Content Area**: Centered max-width with responsive padding.

## 4. Graph Design System
- **Nodes**: Circular or Rounded Rectangles.
- **Edges**: Curved lines, colored by relationship type.
- **Interactions**: Drag-to-move, zoom-to-focus.

## 5. Design System Notes for Stitch Generation
- Use Tailwind classes: `font-display`, `tracking-tight`, `rounded-lg`, `border-slate-200`.
- Maintain a professional high-fidelity look.
- Use `lucide-react` for icons.
