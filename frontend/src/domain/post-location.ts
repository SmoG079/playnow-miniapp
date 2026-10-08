/** Only a linked court supplies the venue location; free posts use their chosen meeting point. */
export function postLocation(post: any) {
  const linked = !!post.venue_id;
  const latitude = linked ? post.venue_latitude : post.latitude;
  const longitude = linked ? post.venue_longitude : post.longitude;
  const address = (linked ? post.venue_address : post.address) || "";
  const title = linked ? (post.venue_name || address || "球场位置待补充")
    : (address || (latitude != null && longitude != null ? `${post.city || ""} · 已选活动地点` : "地点待协商"));
  return { title, address, latitude, longitude };
}
