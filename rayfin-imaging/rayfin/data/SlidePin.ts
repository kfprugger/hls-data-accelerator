import { authenticated, date, decimal, entity, text, uuid } from '@microsoft/rayfin-core';

/**
 * A pinned region of interest on a whole-slide image, shared with everyone signed in to the
 * app. Only the author can change or remove their own pins.
 */
@entity()
@authenticated('read')
@authenticated(['create', 'update', 'delete'], {
  policy: (claims, item) => claims.sub.eq(item.createdBy),
})
export class SlidePin {
  @uuid() id!: string;
  @text({ min: 1, max: 64 }) slideId!: string;
  @text({ min: 1, max: 120 }) title!: string;
  @text({ optional: true, max: 500 }) note?: string;
  @decimal({ precision: 12, scale: 8 }) x!: number;
  @decimal({ precision: 12, scale: 8 }) y!: number;
  @decimal({ precision: 14, scale: 6 }) zoom!: number;
  @text({ max: 128 }) createdBy!: string;
  @text({ max: 128 }) authorName!: string;
  @date() createdAt!: Date;
}
