import {themes as prismThemes} from 'prism-react-renderer';
import type {Config} from '@docusaurus/types';
import type * as Preset from '@docusaurus/preset-classic';

const config: Config = {
  title: 'Agent Harness',
  tagline: 'How AI coding agents work under the hood',
  favicon: 'img/favicon.ico',

  future: {
    v4: true,
  },

  url: 'https://ericchansen.github.io',
  baseUrl: '/agent-harness/',

  organizationName: 'ericchansen',
  projectName: 'agent-harness',

  onBrokenLinks: 'throw',

  i18n: {
    defaultLocale: 'en',
    locales: ['en'],
  },

  presets: [
    [
      'classic',
      {
        docs: {
          routeBasePath: '/',
          sidebarPath: false,
        },
        blog: false,
        theme: {
          customCss: './src/css/custom.css',
        },
      } satisfies Preset.Options,
    ],
  ],

  themeConfig: {
    colorMode: {
      respectPrefersColorScheme: true,
    },
    navbar: {
      title: 'Agent Harness',
      items: [
        {
          href: 'https://github.com/ericchansen/agent-harness',
          label: 'GitHub',
          position: 'right',
        },
        {
          href: 'https://ericchansen.github.io/agent-harness-copilot-sdk/',
          label: 'SDK Variant',
          position: 'right',
        },
      ],
    },
    footer: {
      style: 'dark',
      copyright: `Built for live demos. <a href="https://github.com/ericchansen/agent-harness">Source on GitHub</a>.`,
    },
    prism: {
      theme: prismThemes.github,
      darkTheme: prismThemes.dracula,
      additionalLanguages: ['python', 'json', 'bash'],
    },
  } satisfies Preset.ThemeConfig,
};

export default config;
