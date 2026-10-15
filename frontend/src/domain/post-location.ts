/** Only a linked court supplies the venue location; free posts use their chosen meeting point. */
export function postLocation(post: any) {
  const linked = !!post.venue_id;
  const latitude = linked ? post.venue_latitude : post.latitude;
  const longitude = linked ? post.venue_longitude : post.longitude;
  const address = (linked ? post.venue_address : post.address) || "";
  const title = linked ? (post.venue_name || address || "球场位置待补充")
    : (post.location_name || "地点名称待补充");
  return { title, address, latitude, longitude };
}
