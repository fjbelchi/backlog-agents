## CAT-FRONTEND: Frontend Patterns

Best practices for building accessible, testable, and performant user interfaces.

### Component Decomposition

1. **Each component has a single responsibility.** A component that fetches data, transforms it, and renders a complex layout should be split into a container (data) and presentational (display) components.

2. **Components should be composable.** Design components to accept children, render props, or slots. Small composable pieces are easier to test and reuse than monolithic components.

3. **Keep component files under 200 lines.** If a component exceeds this, extract sub-components or custom hooks/composables. Long files signal mixed responsibilities.

### Accessibility First

4. **Use semantic HTML elements.** `<button>` not `<div onClick>`. `<nav>` not `<div class="nav">`. `<table>` for tabular data, not for layout. Semantic elements provide built-in keyboard and screen reader support.

5. **Add ARIA labels where semantic HTML is insufficient.** Icon-only buttons need `aria-label`. Dynamic content updates need `aria-live`. Custom widgets need appropriate `role` attributes.

6. **Ensure full keyboard navigation.** Every interactive element must be focusable and operable with keyboard alone. Tab order must be logical. Focus traps in modals. Visible focus indicators.

7. **Maintain sufficient color contrast.** WCAG AA requires 4.5:1 for normal text, 3:1 for large text. Do not convey information through color alone -- use icons, patterns, or text labels as well.

### Testing Strategy

8. **Test user interactions, not implementation details.** Use Testing Library queries: `getByRole`, `getByLabelText`, `getByText`. Do not test internal state, refs, or lifecycle methods directly.

9. **Simulate real user behavior in tests.** Click buttons, type in inputs, submit forms. Assert on visible output: rendered text, navigation, DOM changes. If the user cannot see it, do not test it.

10. **Test error states and loading states.** Mock API failures and verify error messages render. Mock slow responses and verify loading indicators appear.

### TypeScript Strict Mode

11. **No `any` types in production code.** Use `unknown` for truly unknown data and narrow with type guards. Every `as any` requires a `// SAFETY:` comment explaining why it is necessary.

12. **Define explicit prop types for every component.** Use interfaces or type aliases. Do not rely on inference for public component APIs. Explicit types serve as documentation.

### State Management

13. **Prefer local component state.** Lift state up only when two or more sibling components need the same data. Global state should be reserved for truly global concerns (auth, theme, locale).

14. **Derive values instead of storing redundant state.** If a value can be computed from existing state, compute it. Redundant state creates synchronization bugs.

### Performance

15. **Lazy-load routes and heavy components.** Use dynamic imports (`React.lazy`, `defineAsyncComponent`) for code that is not needed on initial render. This reduces initial bundle size.

16. **Memoize only where measurement shows benefit.** Do not add `useMemo`, `useCallback`, or `React.memo` everywhere. Profile first, optimize second. Premature memoization adds complexity without measured improvement.
