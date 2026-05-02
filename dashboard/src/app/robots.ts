import { MetadataRoute } from 'next';

export default function robots(): MetadataRoute.Robots {
  return {
    rules: {
      userAgent: '*',
      allow: '/',
      disallow: ['/dashboard/', '/api/'], // Hide internal dashboard and API from search engines
    },
    sitemap: 'https://nimmiai.in/sitemap.xml',
  };
}
