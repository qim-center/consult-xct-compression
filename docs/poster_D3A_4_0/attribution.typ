// #let author = author.author(
//   first-name: "Jeppe",
//   last-name: "Klitgaard",
//   email: "s250250@dtu.dk",
// )
//
#import "deps.typ": jutils
#import jutils.author: author, institution, attribution


// affiliations
#let qim_center = institution(
  name: "Center for Quantification of Imaging Data from MAX IV",
  address: "Kongens Lyngby, Denmark",
)
#let dtu_compute = institution(
  name: "Technical University of Denmark",
  department: "Department of Applied Mathematics and Computer Science",
  address: "Kongens Lyngby, Denmark",
)
#let _3dim_centre = institution(
  name: "Technical University of Denmark",
  department: "3D Imaging Centre",
  address: "Kongens Lyngby, Denmark",
)
#let dtu_physics = institution(
  name: "Technical University of Denmark",
  department: "Department of Physics",
  address: "Kongens Lyngby, Denmark",
)
#let nathist_museum = institution(
  name: "University of Copenhagen",
  department: "Natural History Museum Denmark",
  address: "Copenhagen, Denmark",
)
#let ku_compsci = institution(
  name: "University of Copenhagen",
  department: "Department of Computer Science",
  address: "Copenhagen, Denmark",
)

// Authors

#let jeppe_klitgaard = author(
  first-name: "Jeppe",
  last-name: "Klitgaard",
  email: "s250250@dtu.dk",
  corresponding: true,
  affiliations: (qim_center, dtu_compute,),
)
#let carsten_gundlach = author(
  first-name: "Carsten",
  last-name: "Gundlach",
  affiliations: (_3dim_centre, dtu_physics,),
)
#let christy_anna_hipsley = author(
  first-name: "Christy Anna",
  last-name: "Hipsley",
  affiliations: (nathist_museum,),
)
#let mark_d_scherz = author(
  first-name: "Mark D.",
  last-name: "Scherz",
  affiliations: (nathist_museum,),
)
#let kim_steenstrup_pedersen = author(
  first-name: "Kim",
  last-name: "Steenstrup Pedersen",
  affiliations: (nathist_museum, ku_compsci,),
)
#let felipe_delestro_matos = author(
  first-name: "Felipe Delestro",
  last-name: "Matos",
  affiliations: (qim_center, dtu_compute,),
)
#let anders_bjorholm_dahl = author(
  first-name: "Anders",
  last-name: "Bjorholm Dahl",
  affiliations: (qim_center, dtu_compute, _3dim_centre,),
)
#let jakob_sauer_jørgensen = author(
  first-name: "Jakob Sauer",
  last-name: "Jørgensen",
  affiliations: (qim_center, dtu_compute,),
)

#let authors = attribution(
  jeppe_klitgaard,
  carsten_gundlach,
  christy_anna_hipsley,
  mark_d_scherz,
  kim_steenstrup_pedersen,
  felipe_delestro_matos,
  anders_bjorholm_dahl,
  jakob_sauer_jørgensen,
)
