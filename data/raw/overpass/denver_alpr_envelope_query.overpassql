[out:json][timeout:180][bbox:39.40,-105.40,40.12,-104.35];
(
  nwr["surveillance:type"~"alpr",i];
  nwr[~"^(disused|removed|was|abandoned|planned|proposed|construction|demolished):surveillance:type$"~"alpr",i];
  nwr["manufacturer"~"flock",i];
  nwr["operator"~"flock",i];
  nwr["brand"~"flock",i];
  nwr["camera:type"~"alpr",i];
);
out meta geom;
