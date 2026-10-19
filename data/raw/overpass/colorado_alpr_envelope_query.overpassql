[out:json][timeout:180][bbox:36.70,-109.40,41.30,-101.70];
(
  nwr["surveillance:type"~"alpr",i];
  nwr[~"^(disused|removed|was|abandoned|planned|proposed|construction|demolished):surveillance:type$"~"alpr",i];
  nwr["manufacturer"~"flock",i];
  nwr["operator"~"flock",i];
  nwr["brand"~"flock",i];
  nwr["camera:type"~"alpr",i];
);
out meta geom;
