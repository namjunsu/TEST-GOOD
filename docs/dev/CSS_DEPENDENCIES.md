# CSS Dependencies and Version Compatibility

## Overview
This document tracks CSS selectors and `data-testid` attributes used in our stylesheets to monitor Streamlit version compatibility.

**Last Updated**: 2025-11-14
**Streamlit Compatibility**: 1.29+
**CSS Version**: 2.0

## Critical Dependencies

### 1. Data Test IDs
These selectors depend on Streamlit's internal test IDs:

| Selector | Purpose | Files | Risk Level |
|----------|---------|-------|------------|
| `[data-testid="stSidebar"]` | Sidebar container | main.css, sidebar.css | HIGH |
| `[data-testid="stChatMessageContent"]` | Chat message content | main.css | HIGH |
| `[data-testid="stAppViewContainer"]` | App view container | sidebar.css | MEDIUM |
| `[data-testid="stException"]` | Exception display | main.css | LOW |
| `[data-testid*="chat-message-user"]` | User chat messages | main.css | HIGH |
| `[data-testid*="chat-message-assistant"]` | Assistant messages | main.css | HIGH |

### 2. Streamlit Class Names
These selectors depend on Streamlit's class naming convention:

| Selector | Purpose | Files | Risk Level |
|----------|---------|-------|------------|
| `.stApp` | Main app container | main.css, sidebar.css | HIGH |
| `.stChatMessage` | Chat message wrapper | main.css | HIGH |
| `.stChatFloatingInputContainer` | Chat input area | main.css | HIGH |
| `.stChatInputContainer` | Chat input wrapper | main.css | HIGH |
| `.stButton` | Button components | main.css, sidebar.css | MEDIUM |
| `.stTextInput` | Text input fields | main.css | MEDIUM |
| `.stTextArea` | Text area fields | main.css | MEDIUM |
| `.stSelectbox` | Select box components | main.css | MEDIUM |
| `.stTabs` | Tab components | sidebar.css | MEDIUM |
| `.stAlert` | Alert messages | main.css | LOW |
| `.stException` | Exception messages | main.css | LOW |
| `.stCodeBlock` | Code blocks | main.css | LOW |
| `.streamlit-expanderHeader` | Expander headers | main.css | MEDIUM |
| `.dataframe` | DataFrame display | main.css | LOW |
| `.main .block-container` | Main content container | main.css | MEDIUM |

### 3. BaseWeb Attributes
These selectors depend on BaseWeb UI library used by Streamlit:

| Selector | Purpose | Files | Risk Level |
|----------|---------|-------|------------|
| `[data-baseweb="tab-list"]` | Tab list container | sidebar.css | MEDIUM |
| `[data-baseweb="tab"]` | Individual tabs | sidebar.css | MEDIUM |
| `[data-baseweb="select"]` | Select components | sidebar.css | MEDIUM |
| `[aria-selected="true"]` | Selected tab state | sidebar.css | LOW |

## Version Upgrade Checklist

When upgrading Streamlit, verify these components still work:

### Visual Tests
- [ ] App background gradient displays correctly
- [ ] Glassmorphism effects are visible
- [ ] Chat messages have distinct styling for user/assistant
- [ ] Sidebar buttons have proper hover effects
- [ ] Form inputs have glass effect backgrounds
- [ ] Data tables remain readable with light background
- [ ] Code blocks have dark background
- [ ] Expander components have proper styling

### Functional Tests
- [ ] Chat input field accepts text
- [ ] Buttons respond to hover/click
- [ ] Sidebar scrolling works
- [ ] Theme switching (if implemented)
- [ ] Focus states are visible for accessibility
- [ ] Mobile responsive layout works

### Developer Console Checks
- [ ] No CSS parsing errors
- [ ] No missing selector warnings
- [ ] Backdrop-filter performance is acceptable
- [ ] GPU acceleration is working (check Layers panel)

## CSS Variable System

The updated CSS uses a variable system for easier maintenance:

### Main.css Variables
```css
--primary-gradient-start: #87CEEB
--primary-gradient-end: #1E5FA8
--glass-bg-strong: rgba(255, 255, 255, 0.25)
--text-primary: rgba(255, 255, 255, 0.95)
--blur-light: blur(10px)
--transition-fast: all 0.15s cubic-bezier(0.4, 0, 0.2, 1)
```

### Sidebar.css Variables
```css
--sidebar-text: #FFFFFF
--sidebar-bg-hover: rgba(255, 255, 255, 0.1)
--button-font-size: 13px
--transition: all 0.15s cubic-bezier(0.4, 0, 0.2, 1)
```

## Performance Considerations

1. **Backdrop Filter**: Heavy use of `backdrop-filter` can impact performance on lower-end devices
2. **GPU Acceleration**: Using `transform: translateZ(0)` to force GPU layers
3. **Will-Change**: Applied to elements with frequent backdrop-filter changes
4. **Transitions**: Using cubic-bezier for smoother animations

## Accessibility Features

- Focus visible states with 2px outline
- High contrast mode support
- Reduced motion support
- WCAG AA color contrast (needs verification for some combinations)
- Print styles that remove unnecessary elements

## Known Issues and Workarounds

### Issue: Chat message role detection
**Problem**: Different Streamlit versions use different attributes for chat roles
**Workaround**: Using multiple selectors with wildcards:
```css
[data-testid*="chat-message-user"],
.stChatMessage[data-testid*="user"]
```

### Issue: Deep nesting in form inputs
**Problem**: `.stTextInput > div > div > input` is fragile
**Risk**: Internal structure changes break styling
**Mitigation**: Consider using more general selectors with :has() when widely supported

## Migration Notes

### From v1.0 to v2.0
- Introduced CSS variables for all colors and effects
- Added scoped typography (`.stApp .main` instead of global)
- Separated user/assistant chat message styles
- Added accessibility features (focus states, high contrast)
- Improved performance with GPU hints
- Added responsive design breakpoints
- Consolidated theme management

## Testing Commands

```bash
# Visual regression testing (if implemented)
npm run test:visual

# Check for unused CSS
npm run css:audit

# Validate against Streamlit version
streamlit --version
```

## Contact

For CSS-related issues or updates to this document:
- Create issue in GitHub with label: `frontend`, `css`
- Tag: @frontend-team

## References

- [Streamlit Theming Docs](https://docs.streamlit.io/library/advanced-features/theming)
- [Streamlit CSS Classes (unofficial)](https://github.com/streamlit/streamlit/discussions/css)
- [BaseWeb Components](https://baseweb.design/components/)