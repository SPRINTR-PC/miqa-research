import { css } from "lit";

export const globalStyles = css`
    :host {
        /* TYPOGRAPHY */
        --form-font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
        --form-font-size-base: var(--font-size-base, 1rem);
        --form-font-size-h1: var(--font-size-h1, 1.8rem);
        --form-font-size-h2: var(--font-size-h2, 1.4rem);
        --form-font-size-label: var(--font-size-label, 0.9rem);
        --form-font-size-description: var(--font-size-description, 0.85rem);

        /* COLOURS */
        --mires-color-primary-parts: var(--color-primary-parts, 273 74% 53%);
        --mires-color-secondary-parts: var(--color-secondary-parts, 210 100% 50%);
        --mires-color-text-parts: var(--color-text-parts, 0 0% 20%);
        --mires-color-background-parts: var(--color-background-parts, 0 0% 100%);

        --mires-color-text: var(--color-text, hsl(var(--mires-color-text-parts)));
        --mires-color-background: var(--color-background, hsl(var(--mires-color-background-parts)));
        --mires-color-background-darker: var(--color-background-darker, hsl(from hsl(var(--mires-color-background-parts)) h s calc(l / .5)));

        --mires-form-color-text: hsl(var(--mires-color-text-parts));
        --mires-form-color-input-text: var(--color-input-text, #111);
        --mires-form-color-text-secondary: var(--color-text-secondary, #555); /* För beskrivningar */
        --mires-form-color-text-label: var(--color-text-label, #111);
        --mires-form-color-background: var(--form-color-background, var(--mires-color-background, hsl(0, 0%, 100%)));
        --mires-form-color-background-input-base: var(--color-background-input-base, #ffffff);
        --mires-form-color-background-input-focus: var(--color-background-input-focus, #ffffff);
        --mires-form-color-background-input-ok: var(--color-background-input-base, #b9fb9f);
        --mires-form-color-background-input-ok-focus: var(--color-background-input-focus, #b9fb9f);
        --mires-form-color-background-section: var(--color-background-section, #f9f9f9);
        --mires-form-color-border: var(--color-border, #ccc);
        --mires-form-color-border-focus: var(--form-color-accent);

        /* ACCENT COLOUR (Buttons, active tabs, etc.) */
        --mires-color-primary: var(--color-primary, hsl(var(--mires-color-primary-parts)));
        --mires-color-primary-hover: var(--color-primary-hover, hsl(var(--color-primary-parts, 273 74% 53%) / .5)));
        --color-secondary: hsl(var(--mires-color-secondary-parts));
        --color-secondary-hover: hsl(var(--mires-color-secondary-parts) / .5);
        --form-color-success: var(--color-success, #28a745);
        --form-color-success-darker: var(--color-success-darker, #1e7e34);
        --form-color-success-text: var(--color-success-text, #ffffff);
        --form-color-warning: var(--color-warning, #fbb34e);
        --form-color-warning-darker: var(--color-warning-darker, #fea429);
        --form-color-warning-text: var(--color-warning-text, #ffffff);
        --form-color-neutral: var(--color-neutral, #6c757d);
        --form-color-neutral-darker: var(--color-neutral-darker, #5a6268);
        --form-color-neutral-text: var(--color-neutral-text, #ffffff);
        --form-color-error: var(--color-error, #dc3545);
        --form-color-error-lighter: var(--color-error-lighter, #fa5969);
        --form-color-error-text: var(--color-error-text, #721c24);

        /* STATUS COLOUR (for tolerances) */
        --form-color-required-star: var(--color-required-star, #f98989);
        --form-color-within-tolerance-border: var(--color-within-tolerance-border, #8fff8f);
        --form-color-within-tolerance-background: var(--color-within-tolerance-background, #b9fb9f);
        --form-color-within-tolerance-input-text: var(--color-within-tolerance-input-text, #214521);
        --form-color-within-tolerance-text: var(--color-within-tolerance-text, #3c763d);
        --form-color-out-of-tolerance-border: var(--color-out-of-tolerance-border, #fdf8b2);
        --form-color-out-of-tolerance-background: var(--color-background-input-base, #fff894);
        --form-color-out-of-tolerance-text: var(--color-out-of-tolerance-text, #d9534f);
        --form-color-has-error-border: var(--color-has-error-border, var(--form-color-out-of-tolerance-text));
        --form-color-has-error-background: var(--color-has-error-background, #d58d8b);
        --form-color-out-of-tolerance-warning: var(--form-color-out-of-tolerance-text, yellow);

        /* LAYOUT */
        --form-border-radius: var(--border-radius, 4px);
        --form-spacing-medium: var(--spacing-medium, 1rem);
        --form-spacing-large: var(--spacing-large, 1.5rem);
        --form-button-padding: var(--button-padding, 0.3rem 1rem);

        /* =============================================
        // 2. MAPPNING TO SHOELACE DESIGN TOKENS
        // ============================================= */

        --sl-color-primary-500: var(--form-color-accent);
        --sl-color-primary-600: var(--form-color-accent-darker);

        --sl-color-success-500: var(--form-color-success);
        --sl-color-success-600: var(--form-color-success-darker);

        --sl-color-neutral-500: var(--form-color-neutral);
        --sl-color-neutral-600: var(--form-color-neutral-darker);

        --sl-color-warning-500: var(--form-color-warning);
        --sl-color-warning-600: var(--form-color-warning-darker);

        --sl-font-sans: var(--form-font-family);

        --sl-input-border-color: var(--mires-form-color-border);
        --sl-input-border-color-focus: var(--mires-form-color-border-focus);
        --sl-input-border-radius-medium: var(--form-border-radius);

        /* =============================================
        // 3. GLOBAL STYLING FÖR DENNA KOMPONENT
        // ============================================= */

        font-family: var(--form-font-family, "sans-serif");
        font-size: var(--form-font-size-base);
        color: var(--mires-form-color-text);
        background-color: var(--mires-form-color-background);
        display: block;
        --border: 1px solid var(--mires-form-color-border);
        --border-radius: var(--form-border-radius);
        padding: var(--form-spacing-large);
    }


`;

export const buttonStyles = css`
    .btn {
        padding: var
    }
    .btn {
      background: var(--primary);
      color: white;
      border: none;
      padding: 8px 16px;
      border-radius: 6px;
      font-weight: 500;
      cursor: pointer;
      transition: background 0.2s;
    }

    .btn:hover {
      background: var(--primary-hover);
    }
`;