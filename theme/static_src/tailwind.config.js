// tailwind.config.js
/** @type {import('tailwindcss').Config} */
module.exports = {
    // Use class-based dark mode (optional but flexible)
    darkMode: ['class'],
  
    // Make sure these paths actually reach your project files from THIS file's location
    content: [
      // All Django templates in any app
      '../../**/templates/**/*.html',
      // If you use components/partials outside templates
      '../../templates/**/*.html',
      // If you render classes in JS/TS
      '../../**/static_src/**/*.js',
      // If you build class strings in Python
      '../../**/views/*.py',
      '../../**/urls.py',
    ],
  
    // If Tailwind fights other CSS, turn this on:
    // important: true,
  
    theme: {
      container: {
        center: true,
        padding: {
          DEFAULT: '1rem',
          sm: '1.25rem',
          lg: '2rem',
          xl: '2.5rem',
          '2xl': '3rem',
        },
      },
      extend: {
        // Hook into your CSS variables from base.html
        colors: {
          brand: {
            primary: 'var(--brand-primary)',
            'primary-dark': 'var(--brand-primary-dark)',
            'primary-light': 'var(--brand-primary-light)',
            secondary: 'var(--brand-secondary)',
            surface: 'var(--brand-surface)',
            ink: 'var(--brand-ink)',
          },
        },
        // Add custom spacing and sizing
        spacing: {
          '4.5': '1.125rem',
          '72': '18rem',
          '84': '21rem',
          '96': '24rem',
        },
        // Extend border radius
        borderRadius: {
          '2xl': '1.25rem',
          '3xl': '1.5rem',
        },
        // Add custom grid template columns
        gridTemplateColumns: {
          'footer': 'repeat(auto-fit, minmax(250px, 1fr))',
        },
        // Add backdrop blur
        backdropBlur: {
          'sm': '4px',
          'DEFAULT': '8px',
          'md': '12px',
          'lg': '16px',
        },
      },
    },
  
    // Add core plugins to ensure all utilities are available
    corePlugins: {
      // Enable all core plugins
      container: true,
      // Add any other core plugins you need
    },
  
    // Safelist specific classes that are dynamically generated
    safelist: [
      // Layout
      'container',
      'mx-auto',
      'px-4',
      'py-8',
      'pt-16',
      'pb-8',
      'mb-12',
      'gap-8',
      'gap-12',
      
      // Grid
      'grid',
      'grid-cols-1',
      'grid-cols-2',
      'grid-cols-3',
      'grid-cols-4',
      'md:grid-cols-2',
      'md:grid-cols-4',
      'lg:grid-cols-3',
      'col-span-2',
      'lg:col-span-1',
      'lg:col-span-2',
      
      // Flex
      'flex',
      'flex-col',
      'flex-row',
      'flex-wrap',
      'items-center',
      'items-start',
      'justify-between',
      'justify-center',
      'justify-start',
      
      // Spacing
      'p-2', 'p-4', 'p-6', 'p-8',
      'py-3', 'py-4', 'py-6', 'py-8',
      'px-4', 'px-6',
      'mb-4', 'mb-6', 'mb-8', 'mb-12',
      'mt-2', 'mt-4', 'mt-6',
      'gap-3', 'gap-4', 'gap-8',
      'space-x-3', 'space-x-4',
      'space-y-2', 'space-y-3', 'space-y-4',
      
      // Typography
      'text-sm', 'text-base', 'text-lg', 'text-xl',
      'font-semibold', 'font-bold',
      'text-center', 'text-left', 'text-right',
      'lg:text-left',
      
      // Colors
      'text-white', 'text-gray-300', 'text-gray-400', 'text-gray-500', 'text-gray-600',
      'bg-gray-900', 'bg-black', 'bg-white/5',
      'text-[var(--brand-primary)]', 'text-[var(--brand-primary-dark)]',
      'border-gray-800', 'border-white/10',
      
      // Interactive states
      'hover:bg-gray-800', 'hover:text-white',
      'focus:outline-none', 'focus:ring-2', 'focus:ring-offset-2',
      'focus:ring-[var(--brand-primary)]', 'focus:ring-offset-gray-900',
      
      // Effects
      'transition-colors',
      'backdrop-blur-sm',
      
      // Borders
      'border', 'border-t', 'border-b',
      'rounded-lg', 'rounded-xl',
      
      // Sizing
      'w-full', 'w-auto', 'max-w-xs', 'h-8',
      
      // Display
      'block', 'hidden', 'md:hidden', 'lg:flex',
      
      // Whitespace
      'whitespace-nowrap',
      
      // Placeholder
      'placeholder-gray-400',
      
      // Gradients if you compose them dynamically
      { 
        pattern: /(from|via|to)-(slate|gray|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose)-(100|200|300|400|500|600|700|800|900)/ 
      },
      
      // Common layout helpers that devs toggle in logic
      'inline',
      
      // Common flex utilities
      'items-center', 'justify-between', 'justify-center'
    ],
  
    plugins: [
      require('@tailwindcss/forms'),
      require('@tailwindcss/typography'),
      require('@tailwindcss/aspect-ratio'),
      require('@tailwindcss/line-clamp'),
    ],
  
    future: {
      // Avoids hover styles on touch-only devices
      hoverOnlyWhenSupported: true,
    },
  };
  